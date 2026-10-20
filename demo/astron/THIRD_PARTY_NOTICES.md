# Third-party notices

This folder contains the Windows x64 Astron executable and its runtime DLLs.
The license texts are in [`licenses/`](licenses/).

| Files | Component | License |
| --- | --- | --- |
| `astrond.exe` | Astron | Modified BSD (3-Clause), [`Astron-LICENSE.md`](licenses/Astron-LICENSE.md) |
| `mongocxx.dll`, `bsoncxx.dll` | MongoDB C++ Driver | Apache License 2.0, [`Apache-2.0.txt`](licenses/Apache-2.0.txt) |
| `libmongoc-1.0.dll`, `libbson-1.0.dll` | MongoDB C Driver 1.6.0 | Apache License 2.0 and [`MongoDB-C-Driver-THIRD-PARTY-NOTICES.txt`](licenses/MongoDB-C-Driver-THIRD-PARTY-NOTICES.txt) |
| `libssl-1_1-x64.dll`, `libcrypto-1_1-x64.dll` | OpenSSL 1.1.0c | Dual OpenSSL and original SSLeay licenses, [`OpenSSL-1.1.0c-LICENSE.txt`](licenses/OpenSSL-1.1.0c-LICENSE.txt) |
| `msvcp140.dll`, `vcruntime140.dll` | Microsoft Visual C++ Runtime 14.00.24210.0 | Microsoft redistribution terms; see [Visual Studio 2015 REDIST list](https://learn.microsoft.com/en-us/visualstudio/releases/2015/2015-redistribution-vs) and [Microsoft's redistribution guidance](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files) |

The Astron executable imports the MongoDB and OpenSSL DLLs even though this
demo's Astron configs use the YAML database backend and do not need a MongoDB
server. Keep these DLLs beside `astrond.exe` unless Astron is rebuilt without
those runtime dependencies.

OpenSSL's DLLs also depend on Microsoft's `MSVCR120.dll` (Visual C++ 2013),
which is not included here. Install the x64 Visual C++ 2013 Redistributable if
that runtime is missing from Windows. See [Microsoft's supported VC++
Redistributable downloads](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).

OpenSSL 1.1.0 has been out of support since 2019-09-12 and no longer receives
security updates. The demo configs bind Astron to localhost; rebuild this
legacy binary before exposing it to an untrusted network. See [OpenSSL's
support notice](https://www.openssl-library.org/news/vulnerabilities-1.1.0/).

The Windows executable and DLLs are a historical Astron bundle rebuilt on
2017-03-12. A related public POTCO Astron bundle is preserved at [Pirates-Online-Rewritten,
commit 9331a8f](https://github.com/PiratesOnlineRewritten/Pirates-Online-Rewritten/tree/9331a8f4dc809f0ec5c707ebc596acd54b514ad2/astron).
Its `mongocxx.dll`, `msvcp140.dll`, and `vcruntime140.dll` match these files by
SHA-256; its Astron executable, other MongoDB driver DLLs, and OpenSSL DLLs
differ. Embedded source paths identify the MongoDB C Driver as version 1.6.0,
and the OpenSSL DLL version resources identify 1.1.0c. The MongoDB C++ Driver
DLLs do not expose their release version. The exact public source revision and
build recipe for this bundle are not recorded here.
