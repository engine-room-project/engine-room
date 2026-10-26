import json
import os
from pathlib import Path
import tempfile
import unittest

from engine_room.credentials import Credentials


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"credentials"
        self.store=Credentials(self.root)
    def test_explicit_round_trip_uses_current_platform_protection(self):
        value="synthetic-fixture-only-not-a-provider-token"
        self.store.save("chosen",value)
        self.assertEqual(value,self.store.read("chosen"))
        data=json.loads((self.root/"chosen.json").read_text())
        if os.name=="nt":
            self.assertEqual("dpapi-user",data["format"])
            self.assertNotIn(value,(self.root/"chosen.json").read_text())
        else:
            self.assertEqual(0,(self.root/"chosen.json").stat().st_mode&0o077)
    def test_no_automatic_fallback_to_another_reference(self):
        self.store.save("other-application", "synthetic-other-value")
        with self.assertRaisesRegex(ValueError,"explicitly selected"): self.store.read("missing")
    def test_replacement_must_be_explicit(self):
        self.store.save("chosen","synthetic-one")
        with self.assertRaises(ValueError): self.store.save("chosen","synthetic-two")
        self.assertEqual("synthetic-one",self.store.read("chosen"))
        self.store.save("chosen","synthetic-two",overwrite=True)
        self.assertEqual("synthetic-two",self.store.read("chosen"))
    def test_invalid_references_and_line_breaks_fail(self):
        for reference,value in [("../outside","synthetic"),("chosen","synthetic\nheader"),("chosen","")]:
            with self.assertRaises(ValueError): self.store.save(reference,value)
        self.assertEqual([],list(self.root.iterdir()))
    def test_corrupt_record_does_not_expose_its_contents(self):
        (self.root/"chosen.json").write_text('{"value":"synthetic-sensitive-content"',encoding="utf-8")
        if os.name!="nt": (self.root/"chosen.json").chmod(0o600)
        with self.assertRaises(ValueError) as error: self.store.read("chosen")
        self.assertNotIn("sensitive",str(error.exception))
    @unittest.skipIf(os.name=="nt","POSIX permission boundary")
    def test_shared_permissions_refused(self):
        self.store.save("chosen","synthetic-value")
        (self.root/"chosen.json").chmod(0o644)
        with self.assertRaises(ValueError): self.store.read("chosen")
        (self.root/"chosen.json").chmod(0o600)
        self.root.chmod(0o755)
        with self.assertRaises(ValueError): Credentials(self.root)


if __name__=="__main__": unittest.main()
