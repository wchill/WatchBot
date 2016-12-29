import os

PROJECT_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


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

    def get_files_in_current_dir(self):
        files = []
        for entry in os.scandir(self._current_path):
            if self.is_safe_path(entry.path) and entry.is_file():
                files.append(entry)
        return files

    def get_dirs_in_current_dir(self):
        dirs = []
        for entry in os.scandir(self._current_path):
            if self.is_safe_path(entry.path) and entry.is_dir():
                dirs.append(entry)
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

    def list_filenames_in_current_dir(self):
        return [entry.name for entry in self.get_files_in_current_dir()]

    def list_dirnames_in_current_dir(self):
        return [entry.name for entry in self.get_dirs_in_current_dir()]

    def get_complete_path(self, relative_path):
        complete_path = os.path.join(self._current_path, relative_path)
        return complete_path

    def file_exists(self, path, relative=True):
        if relative:
            new_absolute_path = os.path.join(self._current_path, path)
        else:
            new_absolute_path = path
        return self.is_safe_path(new_absolute_path) and os.path.exists(new_absolute_path) and os.path.isfile(new_absolute_path)

    def list_nonhidden_filenames_in_current_dir(self):
        return [entry.name for entry in self.get_files_in_current_dir() if entry.name[0] != '.']

    def list_nonhidden_dirnames_in_current_dir(self):
        return [entry.name for entry in self.get_dirs_in_current_dir() if entry.name[0] != '.']

    @staticmethod
    def filter_filenames_by_ext(filenames, extensions):
        filtered_filenames = [f for f in filenames if os.path.splitext(f)[1] in extensions]
        return filtered_filenames
