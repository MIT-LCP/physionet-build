import os
import subprocess
import logging
from django.core.exceptions import ValidationError

LOGGER = logging.getLogger(__name__)


class FileUnpacker:
    """
    Utility class for unpacking compressed files in project directories
    """

    SUPPORTED_EXTENSIONS = {
        '.tar.gz': 'tar',
        '.tgz': 'tar',
        '.tar.bz2': 'tar',
        '.tar.xz': 'tar',
        '.zip': 'zip',
        '.gz': 'gzip',
        '.bz2': 'bzip2',
        '.xz': 'xz'
    }

    @classmethod
    def get_archive_type(cls, file_path):
        """
        Determine the archive type based on file extension
        """
        for ext in cls.SUPPORTED_EXTENSIONS:
            if file_path.endswith(ext):
                return cls.SUPPORTED_EXTENSIONS[ext]
        return None

    @classmethod
    def unpack_file(cls, project_root, file_path, target_directory=None, overwrite_existing=False):
        """
        Unpack a compressed file in the project directory

        Args:
            project_root: Root directory of the project
            file_path: Relative path to the compressed file within the project
            target_directory: Optional target directory for extraction
            overwrite_existing: Whether to overwrite existing files

        Returns:
            dict: Result information including success status and extracted files
        """
        full_file_path = os.path.join(project_root, file_path)

        if not os.path.exists(full_file_path):
            raise ValidationError(f"File not found: {file_path}")

        if not os.path.isfile(full_file_path):
            raise ValidationError(f"Path is not a file: {file_path}")

        archive_type = cls.get_archive_type(file_path)
        if not archive_type:
            raise ValidationError(f"Unsupported file type: {file_path}")

        # Determine target directory
        if target_directory:
            extract_dir = os.path.join(project_root, target_directory)
            if not os.path.exists(extract_dir):
                os.makedirs(extract_dir, exist_ok=True)
        else:
            # Extract to the same directory as the archive
            extract_dir = os.path.dirname(full_file_path)

        try:
            if archive_type == 'tar':
                return cls._extract_tar(full_file_path, extract_dir, overwrite_existing)
            elif archive_type == 'zip':
                return cls._extract_zip(full_file_path, extract_dir, overwrite_existing)
            elif archive_type in ['gzip', 'bzip2', 'xz']:
                return cls._extract_single_file(full_file_path, extract_dir, overwrite_existing)
            else:
                raise ValidationError(f"Unsupported archive type: {archive_type}")
        except Exception as e:
            LOGGER.error(f"Error unpacking {file_path}: {str(e)}")
            raise ValidationError(f"Failed to unpack file: {str(e)}")

    @classmethod
    def _extract_tar(cls, file_path, extract_dir, overwrite_existing):
        """
        Extract a tar archive
        """
        flags = ['-xf']
        if overwrite_existing:
            flags.append('--overwrite')

        cmd = ['tar'] + flags + [file_path, '-C', extract_dir]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=extract_dir,
                timeout=300  # 5 minute timeout
            )

            if result.returncode != 0:
                raise subprocess.CalledProcessError(
                    result.returncode, cmd, result.stdout, result.stderr
                )

            # Get list of extracted files
            extracted_files = cls._list_extracted_files(extract_dir, file_path)

            return {
                'success': True,
                'extracted_files': extracted_files,
                'extract_directory': extract_dir
            }

        except subprocess.TimeoutExpired:
            raise ValidationError("Extraction timed out. The archive may be very large.")
        except subprocess.CalledProcessError as e:
            raise ValidationError(f"Tar extraction failed: {e.stderr}")

    @classmethod
    def _extract_zip(cls, file_path, extract_dir, overwrite_existing):
        """
        Extract a zip archive
        """
        # Quiet mode
        flags = ['-q']
        if overwrite_existing:
            # Overwrite without prompting
            flags.append('-o')

        cmd = ['unzip'] + flags + [file_path, '-d', extract_dir]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=extract_dir,
                timeout=300  # 5 minute timeout
            )

            if result.returncode != 0:
                raise subprocess.CalledProcessError(
                    result.returncode, cmd, result.stdout, result.stderr
                )

            extracted_files = cls._list_extracted_files(extract_dir, file_path)

            return {
                'success': True,
                'extracted_files': extracted_files,
                'extract_directory': extract_dir
            }

        except subprocess.TimeoutExpired:
            raise ValidationError("Extraction timed out. The archive may be very large.")
        except subprocess.CalledProcessError as e:
            raise ValidationError(f"Zip extraction failed: {e.stderr}")

    @classmethod
    def _extract_single_file(cls, file_path, extract_dir, overwrite_existing):
        """
        Extract a single compressed file (gzip, bzip2, xz)
        """
        filename = os.path.basename(file_path)
        base_name = filename

        # Remove compression extensions
        for ext in ['.gz', '.bz2', '.xz']:
            if base_name.endswith(ext):
                base_name = base_name[:-len(ext)]
                break

        output_path = os.path.join(extract_dir, base_name)

        if os.path.exists(output_path) and not overwrite_existing:
            raise ValidationError(f"File already exists: {base_name}")

        # Determine decompression command
        if file_path.endswith('.gz'):
            cmd = ['gunzip', '-c', file_path]
        elif file_path.endswith('.bz2'):
            cmd = ['bunzip2', '-c', file_path]
        elif file_path.endswith('.xz'):
            cmd = ['unxz', '-c', file_path]
        else:
            raise ValidationError(f"Unsupported compression type: {file_path}")

        try:
            with open(output_path, 'wb') as output_file:
                result = subprocess.run(
                    cmd,
                    stdout=output_file,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=300  # 5 minute timeout
                )

            if result.returncode != 0:
                os.remove(output_path)  # Clean up failed extraction
                raise subprocess.CalledProcessError(
                    result.returncode, cmd, stderr=result.stderr
                )

            return {
                'success': True,
                'extracted_files': [base_name],
                'extract_directory': extract_dir
            }

        except subprocess.TimeoutExpired:
            if os.path.exists(output_path):
                os.remove(output_path)
            raise ValidationError("Extraction timed out. The file may be very large.")
        except subprocess.CalledProcessError as e:
            if os.path.exists(output_path):
                os.remove(output_path)
            raise ValidationError(f"Extraction failed: {e.stderr}")

    @classmethod
    def _list_extracted_files(cls, extract_dir, original_file):
        """
        List files that were extracted (excluding the original archive)
        """
        extracted_files = []
        original_filename = os.path.basename(original_file)

        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file != original_filename:
                    rel_path = os.path.relpath(os.path.join(root, file), extract_dir)
                    extracted_files.append(rel_path)

        return sorted(extracted_files)

    @classmethod
    def validate_file_path(cls, project_root, file_path):
        """
        Validate that a file path is safe and exists
        """
        # Prevent directory traversal
        if '..' in file_path or file_path.startswith('/'):
            raise ValidationError("Invalid file path")

        full_path = os.path.join(project_root, file_path)

        # Ensure the path is within the project directory
        try:
            full_path = os.path.realpath(full_path)
            project_root = os.path.realpath(project_root)
            if not full_path.startswith(project_root):
                raise ValidationError("File path is outside project directory")
        except (OSError, ValueError):
            raise ValidationError("Invalid file path")

        return full_path
