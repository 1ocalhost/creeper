# Build Trojan

## dependency files

download these:

```text
https://github.com/Kitware/CMake/releases/download/v4.0.1/cmake-4.0.1-windows-x86_64.msi
https://github.com/StrawberryPerl/Perl-Dist-Strawberry/releases/download/SP_54001_64bit_UCRT/strawberry-perl-5.40.0.1-64bit.msi
https://github.com/openssl/openssl/releases/download/OpenSSL_1_1_1w/openssl-1.1.1w.tar.gz
https://archives.boost.io/release/1.88.0/source/boost_1_88_0.tar.gz
https://github.com/trojan-gfw/trojan/archive/refs/tags/v1.16.0.tar.gz
```
then install Perl and CMake

> Execute following command in the "Developer Command Prompt for VS"

## openssl
```shell
perl Configure no-shared VC-WIN32 --prefix=C:\openssl
nmake
nmake install
```

## boost

extract tar file to "C:/boost_1_88_0"

```shell
bootstrap.bat
b2 --build-dir=build --stagedir=stage --toolset=msvc address-model=32 link=static runtime-link=static threading=multi variant=release
```

## trojan

just extract "src" and "CMakeLists.txt"

```shell
mkdir build
cd build
cmake -DENABLE_MYSQL=OFF -DENABLE_SSL_KEYLOG=OFF -DBoost_USE_STATIC_LIBS=ON -DBOOST_ROOT="C:/boost_1_88_0" -DBOOST_LIBRARYDIR="C:/boost_1_88_0/stage/lib" -DOPENSSL_ROOT_DIR="C:/openssl" -DCMAKE_CXX_FLAGS_RELEASE="/D_WIN32_WINNT=0x0601 /MT /O2 /Ob2 /DNDEBUG" -G "Visual Studio 17 2022" -A Win32 ..
cmake --build . --config Release
```
