import json
import subprocess
import tempfile
import unittest
from worker.inventory import checksum, clean_entries, validate_inventory
from worker.engine import Engine, DISCLOSURE

class InventoryTests(unittest.TestCase):
    def export(self, rows):
        return json.loads(subprocess.check_output(['node','--input-type=module','-e',
            "import {exportInventory} from './companion/inventory.js'; let s='';for await(const c of process.stdin)s+=c; console.log(JSON.stringify(await exportInventory(JSON.parse(s))));"],
            input=json.dumps(rows),text=True))
    def test_real_companion_exports_import_through_engine(self):
        cases = [['é'],['a','Z'],['😀','\ue000','汉字'],['same','same'],['x'*99+'😀'+'Z'],['\ud800','a\n"\\'],['\x7f','\u2028','\u2029']]
        with tempfile.TemporaryDirectory() as d:
            e=Engine(d,lambda:[])
            try:
                e.start({'accepted':True,'version':DISCLOSURE,'extensions':True})
                for names in cases:
                    with self.subTest(names=names):
                        rows=[{'name':n,'enabled':bool(i%2)} for i,n in enumerate(names)]
                        exported=self.export(rows)
                        result=e.import_extensions(exported)
                        self.assertTrue(result['checksum_verified'])
                        self.assertFalse(result['browser_authenticated'])
                        self.assertEqual(e.context['extensions'],clean_entries(rows))
            finally:e.stop();e.store.db.close()
    def test_v2_sort_is_independent_of_input_order(self):
        rows=[{'name':'same','enabled':True},{'name':'same','enabled':False},{'name':'é','enabled':True}]
        self.assertEqual(self.export(rows)['digest'],self.export(rows[::-1])['digest'])
    def test_tampering_is_rejected(self):
        data=self.export([{'name':'é','enabled':True}]);data['extensions'][0]['enabled']=False
        with self.assertRaisesRegex(ValueError,'does not match'):validate_inventory(data)
    def test_missing_malformed_checksum_and_unknown_versions_rejected(self):
        for data in [{'format':'iim.extensions.v2','extensions':[]},{'extensions':[],'digest':3},{'extensions':[],'digest':''},{'format':'unknown','extensions':[]}]:
            with self.subTest(data=data),self.assertRaises(ValueError):validate_inventory(data)
    def test_legacy_python_checksums_remain_supported(self):
        rows=[{'name':'é','enabled':True}]
        self.assertTrue(validate_inventory({'format':'iim.extensions.v1','extensions':rows,'digest':checksum(rows,'iim.extensions.v1')})[1])
    def test_unsigned_legacy_inventory_is_explicit(self):
        self.assertFalse(validate_inventory([])[1])
