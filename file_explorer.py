import os

PROJECT_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


class PseudoDirEntry:
    def __init__(self, name, scandir_path):
        self.name = name
        self._scandir_path = scandir_path
        self.path = os.path.join(scandir_path, name)
        self._stat = dict()
        self._is_symlink = None
        self._is_file = dict()
        self._is_dir = dict()

    def inode(self):
        if False not in self._stat:
            self._stat[False] = self.stat(follow_symlinks=False)
        return self._stat[False].st_ino

    def is_dir(self, *, follow_symlinks=True):
        if follow_symlinks not in self._is_dir:
            self._is_dir[follow_symlinks] = os.path.isdir(self.path) and (follow_symlinks or not self.is_symlink)
        return self._is_file[follow_symlinks]

    def is_file(self, *, follow_symlinks=True):
        if follow_symlinks not in self._is_file:
            self._is_file[follow_symlinks] = os.path.isfile(self.path) and (follow_symlinks or not self.is_symlink)
        return self._is_file[follow_symlinks]

    def is_symlink(self):
        if self._is_symlink is None:
            self._is_symlink = os.path.islink(self.path)
        return self._is_symlink

    def stat(self, *, follow_symlinks=True):
        if follow_symlinks not in self._stat:
            self._stat[follow_symlinks] = os.stat(self.path, follow_symlinks=follow_symlinks)
        return self._stat[follow_symlinks]


class FileExplorer(object):
    def __init__(self, root_path=None):
        self._root_path = os.path.realpath(root_path) if root_path else PROJECT_ROOT_DIR
        self._current_path = self._root_path

    def is_safe_path(self, path, follow_symlinks=True):
        # resolves symbolic links
        if follow_symlinks:
            return os.path.realpath(path).startswith(os.path.realpath(self._root_path))

        return os.path.abspath(path).startswith(self._root_path)

    def get_root_path(self):
        return self._root_path

    def get_current_path(self, relative=True):
        if relative:
            my_path = os.path.relpath(self._current_path, self._root_path)
            if my_path == '.':
                return '/'
            else:
                return '/' + my_path
        return self._current_path

    def build_absolute_path(self, offset_abs_path):
        return os.path.join(self._root_path, offset_abs_path)

    def get_files_in_current_dir(self, hidden=False, extensions=None):
        files = []
        for entry in os.scandir(self._current_path):
            if self.is_safe_path(entry.path) and entry.is_file() and (hidden or entry.name[0] != '.'):
                if extensions is None or os.path.splitext(entry.name)[1] in extensions:
                    files.append(entry)
        return files

    def get_dirs_in_current_dir(self, hidden=False):
        dirs = []
        for entry in os.scandir(self._current_path):
            if self.is_safe_path(entry.path) and entry.is_dir() and (hidden or entry.name[0] != '.'):
                dirs.append(entry)
        if self.is_safe_path(self.get_complete_path('..')):
            dirs.append(PseudoDirEntry('..', self._current_path))
        print(dirs)
        return dirs

    def change_directory(self, path, relative=True):
        if relative:
            new_absolute_path = os.path.join(self._current_path, path)
        else:
            new_absolute_path = path

        if self.is_safe_path(new_absolute_path) and os.path.exists(new_absolute_path):
            self._current_path = new_absolute_path
            return True

        return False

    def change_to_root_dir(self):
        return self.change_directory(self._root_path, relative=False)

    def get_complete_path(self, relative_path):
        complete_path = os.path.join(self._current_path, relative_path)
        return complete_path

    def file_exists(self, path, relative=True):
        if relative:
            new_absolute_path = os.path.join(self._current_path, path)
        else:
            new_absolute_path = path
        return self.is_safe_path(new_absolute_path) and os.path.exists(new_absolute_path) and os.path.isfile(new_absolute_path)

    @staticmethod
    def filter_filenames_by_ext(filenames, extensions):
        filtered_filenames = [f for f in filenames if os.path.splitext(f)[1] in extensions]
        return filtered_filenames
