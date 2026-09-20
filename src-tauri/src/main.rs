#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::{Child, ChildStdin, Command, Stdio},
    sync::{mpsc, Mutex},
    time::Duration,
};
use serde::{Deserialize, Serialize};
use tauri::Manager;

#[cfg(windows)]
mod job {
    use std::os::windows::io::AsRawHandle;
    use std::os::windows::raw::HANDLE;
    use std::process::Child;
    use std::ptr;

    type BOOL = i32;
    type DWORD = u32;
    type ULONG_PTR = usize;

    const JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: DWORD = 0x2000;
    const JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS: DWORD = 9;

    #[repr(C)]
    struct IoCounters {
        read_operation_count: u64,
        write_operation_count: u64,
        other_operation_count: u64,
        read_transfer_count: u64,
        write_transfer_count: u64,
        other_transfer_count: u64,
    }

    #[repr(C)]
    struct JobObjectBasicLimitInformation {
        per_process_user_time_limit: i64,
        per_job_user_time_limit: i64,
        limit_flags: DWORD,
        minimum_working_set_size: usize,
        maximum_working_set_size: usize,
        active_process_limit: DWORD,
        affinity: ULONG_PTR,
        priority_class: DWORD,
        scheduling_class: DWORD,
    }

    #[repr(C)]
    struct JobObjectExtendedLimitInformation {
        basic_limit_information: JobObjectBasicLimitInformation,
        io_info: IoCounters,
        process_memory_limit: usize,
        job_memory_limit: usize,
        peak_process_memory_used: usize,
        peak_job_memory_used: usize,
    }

    extern "system" {
        fn CreateJobObjectW(lp_job_attributes: *mut std::ffi::c_void, lp_name: *const u16) -> HANDLE;
        fn SetInformationJobObject(
            h_job: HANDLE,
            job_object_info_class: DWORD,
            lp_job_object_info: *const std::ffi::c_void,
            cb_job_object_info_length: DWORD,
        ) -> BOOL;
        fn AssignProcessToJobObject(h_job: HANDLE, h_process: HANDLE) -> BOOL;
        fn CloseHandle(h_object: HANDLE) -> BOOL;
    }

    pub struct WindowsJob(HANDLE);

    // Safety: The Win32 Job Object handle is owned solely by this struct and
    // is safe to send between threads when wrapped in the runtime Mutex.
    unsafe impl Send for WindowsJob {}

    impl WindowsJob {
        pub fn create() -> Option<Self> {
            unsafe {
                let handle = CreateJobObjectW(ptr::null_mut(), ptr::null());
                if handle.is_null() {
                    return None;
                }
                let mut info: JobObjectExtendedLimitInformation = std::mem::zeroed();
                info.basic_limit_information.limit_flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                let res = SetInformationJobObject(
                    handle,
                    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                    &info as *const _ as *const std::ffi::c_void,
                    std::mem::size_of::<JobObjectExtendedLimitInformation>() as DWORD,
                );
                if res == 0 {
                    CloseHandle(handle);
                    return None;
                }
                Some(WindowsJob(handle))
            }
        }

        pub fn assign_child(&self, child: &Child) -> bool {
            unsafe {
                let process_handle = child.as_raw_handle() as HANDLE;
                AssignProcessToJobObject(self.0, process_handle) != 0
            }
        }
    }

    impl Drop for WindowsJob {
        fn drop(&mut self) {
            unsafe {
                if !self.0.is_null() {
                    CloseHandle(self.0);
                }
            }
        }
    }
}

#[derive(Clone, Serialize, Deserialize)]
struct Connection {
    endpoint: String,
    token: String,
}

struct Worker {
    child: Child,
    input: Option<ChildStdin>,
    connection: Connection,
    #[cfg(windows)]
    _job: Option<job::WindowsJob>,
}

#[derive(Default)]
struct Runtime {
    worker: Mutex<Option<Worker>>,
}

impl Drop for Worker {
    fn drop(&mut self) {
        // EOF requests graceful cleanup; then bound shutdown if a native API hangs.
        self.input.take();
        for _ in 0..30 {
            if matches!(self.child.try_wait(), Ok(Some(_))) {
                return;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn resolve_python(root: &Path) -> PathBuf {
    // 1. Explicit developer/operator override
    if let Some(p) = std::env::var_os("IIM_PYTHON") {
        let path = PathBuf::from(p);
        if path.exists() {
            return path;
        }
    }

    // 2. Project local virtual environment (.venv)
    #[cfg(windows)]
    let venv_python = root.join(".venv").join("Scripts").join("python.exe");
    #[cfg(not(windows))]
    let venv_python = root.join(".venv").join("bin").join("python");
    if venv_python.exists() {
        return venv_python;
    }

    // 3. Bundled sidecar runtime inside binaries/python/
    #[cfg(windows)]
    {
        let sidecar_python = root.join("binaries").join("python").join("python.exe");
        if sidecar_python.exists() {
            return sidecar_python;
        }
        let sidecar_scripts = root.join("binaries").join("python").join("Scripts").join("python.exe");
        if sidecar_scripts.exists() {
            return sidecar_scripts;
        }
    }
    #[cfg(not(windows))]
    {
        let sidecar_python = root.join("binaries").join("python").join("bin").join("python3");
        if sidecar_python.exists() {
            return sidecar_python;
        }
    }

    // 4. Bundled sidecar relative to current executable
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            #[cfg(windows)]
            {
                let exe_sidecar = exe_dir.join("binaries").join("python").join("python.exe");
                if exe_sidecar.exists() {
                    return exe_sidecar;
                }
                let exe_scripts = exe_dir.join("binaries").join("python").join("Scripts").join("python.exe");
                if exe_scripts.exists() {
                    return exe_scripts;
                }
            }
            #[cfg(not(windows))]
            {
                let exe_sidecar = exe_dir.join("binaries").join("python").join("bin").join("python3");
                if exe_sidecar.exists() {
                    return exe_sidecar;
                }
            }
        }
    }

    // 5. System PATH fallback
    if cfg!(windows) {
        PathBuf::from("python")
    } else {
        PathBuf::from("python3")
    }
}

#[tauri::command]
async fn bootstrap(
    app: tauri::AppHandle,
    window: tauri::WebviewWindow,
    runtime: tauri::State<'_, Runtime>,
) -> Result<Connection, String> {
    if window.label() != "main" {
        return Err("Untrusted window".into());
    }
    let mut state = runtime.worker.lock().map_err(|_| "Runtime lock failed")?;
    if let Some(worker) = state.as_mut() {
        if worker
            .child
            .try_wait()
            .map_err(|_| "Worker status unavailable")?
            .is_none()
        {
            return Ok(worker.connection.clone());
        }
    }
    let root = if cfg!(debug_assertions) {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .to_path_buf()
    } else {
        app.path()
            .resource_dir()
            .map_err(|_| "Resources unavailable")?
    };

    let python = resolve_python(&root);
    let mut command = Command::new(&python);
    command
        .args(["-m", "worker.server"])
        .current_dir(root)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }

    let mut child = command.spawn().map_err(|e| {
        format!(
            "Cannot start Python worker at '{}': {}. Check requirements or set IIM_PYTHON.",
            python.display(),
            e
        )
    })?;

    #[cfg(windows)]
    let job = {
        let job = job::WindowsJob::create();
        if let Some(ref j) = job {
            let _ = j.assign_child(&child);
        }
        job
    };

    let mut input = child.stdin.take().ok_or("Worker input unavailable")?;
    let token = format!(
        "{}{}",
        uuid::Uuid::new_v4().simple(),
        uuid::Uuid::new_v4().simple()
    );
    let data_dir = app
        .path()
        .app_local_data_dir()
        .map_err(|_| "App data directory unavailable")?;
    let config = serde_json::json!({
        "token": token,
        "data_dir": data_dir,
        "dev": cfg!(debug_assertions)
    });

    if writeln!(input, "{}", config)
        .and_then(|_| input.flush())
        .is_err()
    {
        let _ = child.kill();
        let _ = child.wait();
        return Err("Worker startup failed".into());
    }

    let output = child.stdout.take().ok_or("Worker output unavailable")?;
    let (tx, rx) = mpsc::channel();
    std::thread::spawn(move || {
        let mut line = String::new();
        let result = BufReader::new(output).read_line(&mut line).map(|_| line);
        let _ = tx.send(result);
    });

    let line = match rx.recv_timeout(Duration::from_secs(10)) {
        Ok(Ok(line)) => line,
        _ => {
            let _ = child.kill();
            let _ = child.wait();
            return Err("Worker startup timed out; check Python dependencies".into());
        }
    };

    let connection: Connection = match serde_json::from_str(&line) {
        Ok(c) => c,
        Err(_) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err("Worker handshake failed".into());
        }
    };

    *state = Some(Worker {
        child,
        input: Some(input),
        connection: connection.clone(),
        #[cfg(windows)]
        _job: job,
    });

    Ok(connection)
}

fn main() {
    let app = tauri::Builder::default()
        .manage(Runtime::default())
        .invoke_handler(tauri::generate_handler![bootstrap, save_export])
        .build(tauri::generate_context!())
        .expect("Unable to start desktop app");

    app.run(|handle, event| {
        match event {
            tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit => {
                if let Ok(mut state) = handle.state::<Runtime>().worker.lock() {
                    state.take();
                }
            }
            _ => {}
        }
    });
}

#[tauri::command]
fn save_export(
    app: tauri::AppHandle,
    window: tauri::WebviewWindow,
    name: String,
    bytes: Vec<u8>,
) -> Result<String, String> {
    if window.label() != "main"
        || bytes.len() > 16 * 1024 * 1024
        || name.len() > 100
        || !name
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.')
        || !(name.ends_with(".json") || name.ends_with(".pdf"))
    {
        return Err("Invalid export".into());
    }
    let directory = app
        .path()
        .download_dir()
        .map_err(|_| "Downloads folder unavailable")?;
    let path = directory.join(format!("{}-{}", uuid::Uuid::new_v4().simple(), name));
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&path)
        .map_err(|_| "Cannot create export in Downloads")?;
    file.write_all(&bytes).map_err(|_| "Export write failed")?;
    Ok(path.to_string_lossy().into_owned())
}

