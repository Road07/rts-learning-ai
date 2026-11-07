"""GUI's inherited PATH need not contain the shell's bundled Git."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from engine_update import git_executable

class GitResolutionChecks(unittest.TestCase):
    def test_path_git_is_preferred(self):
        with patch('engine_update.shutil.which',return_value='installed/git.exe'):
            self.assertEqual(git_executable(),'installed/git.exe')

    def test_empty_gui_path_uses_installed_runtime(self):
        with patch.dict(os.environ,{'PATH':''}),patch('engine_update.Path.is_file',return_value=True):
            self.assertEqual(Path(git_executable()),Path(sys.executable).parent.parent/'native/git/cmd/git.exe')

if __name__=='__main__':unittest.main()
