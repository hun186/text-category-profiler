# Historical FTPTEST marker

This original 3-byte text file was moved byte-for-byte out of the application
package, from text_category_profiler/FTPTEST/abc.txt, to the present directory.
The original Git blob identity, byte size and path mapping are retained in
experiments/fixtures/bl001_residual_inventory.json (schema v6).

An independent historical deployment snapshot in the TRV_deploy tree retains
its identical copy, and was not changed by this work.

The only tracked first-party Python file that names abc.txt is
DatasetConverter/DataConverter.py, where it appears in a nonexecuting
triple-quoted rowlist sample example. There is no verified file open or FTP
operation at that site. This static finding does not rule out dynamic paths,
non-Python scripts, external/manual users, or unknown deployment references.
Such callers must update their paths explicitly if they used the old location.

The marker's original provenance, purpose and usage rights are unverified.
The relocation does not perform FTP activity or real pipeline processing.
BL-001 stays In Progress until further verification.
