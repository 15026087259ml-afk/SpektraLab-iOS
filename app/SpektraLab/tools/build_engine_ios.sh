#!/bin/bash
# build_engine_ios.sh -- the SpektraLab engine (engine/) for the iOS app (SpektraLab-iOS).
#
#   app/SpektraLab/tools/build_engine_ios.sh
#
# Leaves build/engine-iphoneos/{libspektralab_engine.a, EngineResources/} and the same under
# build/engine-iphonesimulator/ -- the folder names are the $PLATFORM_NAME of the two builds the
# iOS target makes, which gen_project.py links and copies into the app.
#
# It compiles engine/ exactly as tools/build_engine_mac.sh does -- the same sources, -O2, and the
# kernels with safe math (engine/build.sh's trap 1; spk_engine_create refuses a fast-math metallib)
# -- only for the *-apple-ios18.0 targets, because an iOS app cannot link a macabi or plain macOS
# object. Nothing in engine/ is changed for it (IOS-PORT-NOTES.md §3: the compiled set is POSIX
# dispatch and Accelerate, all iOS frameworks), and the app calls the engine's own C ABI
# (engine/include/spektralab/spk_engine.h) with nothing in between. The resources are
# engine/build.sh's `bundle_resources`, verbatim, the same files the Mac bundle carries.
#
# The kernels are built once: air64-apple-ios18.0 loads on the device and on the simulator alike,
# so both EngineResources carry the same metallib. The .metalar is baked by a *host* tool
# (engine/tools/build_metal_archive.sh, macosx SDK), which is why this script needs a Mac and no
# iOS toolchain beyond Xcode's own.
set -euo pipefail
here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
root=$(cd "$here/../.." && pwd)
eng="$root/engine"
out_dev="$here/build/engine-iphoneos"          # $PLATFORM_NAME of an iOS device build
out_sim="$here/build/engine-iphonesimulator"   # …and of a simulator build
rm -rf "$out_dev" "$out_sim"
mkdir -p "$out_dev/obj" "$out_dev/air" "$out_sim/obj"

sdk_dev=$(xcrun --sdk iphoneos --show-sdk-path)
sdk_sim=$(xcrun --sdk iphonesimulator --show-sdk-path)
# The iOS app's floor is iOS 18 (gen_project.py; the shared tree's recognisers are iOS 18+), which the kernels are stamped for. A metallib
# stamped for a newer iOS than the device's does not load -- the app opens and cannot render --
# so the stamp is read back below, as engine/build.sh does for macOS.
IOS_MIN=18.0
includes=(-I"$eng/include" -I"$eng/src" -I"$eng/src/core" -I"$eng/third_party/metal-cpp")
shopt -s nullglob
sources=("$eng"/src/core/*.cpp "$eng"/src/gpu/*.cpp "$eng"/src/pipeline/*.cpp)
shopt -u nullglob

# One slice per destination: the device is arm64; the simulator is the arm64 of an Apple-silicon
# Mac (the only hosts Xcode 27 installs on) -- an Intel Mac's simulator is out of this port's
# scope, as it is for the Catalyst builds, which dropped x86_64 the same way.
build_slice() {  # $1 = obj dir, $2 = target triple, $3 = sdk path
  local objdir=$1 target=$2 sdk=$3
  mkdir -p "$objdir"
  local cxxflags=(-target "$target" -isysroot "$sdk" -std=c++20 -O2 -Wall -Wextra)
  local pids=() objs=()
  for src in "${sources[@]}"; do
    local o="$objdir/$(basename "$src" .cpp).o"
    objs+=("$o")
    "$cxx" "${cxxflags[@]}" "${includes[@]}" -c "$src" -o "$o" 2> "$o.log" &
    pids+=($!)
  done
  local failed=0
  for i in "${!pids[@]}"; do
    if ! wait "${pids[$i]}"; then echo "FAIL ${objs[$i]}"; cat "${objs[$i]}.log"; failed=1; fi
  done
  [[ $failed == 0 ]] || exit 1
  xcrun --sdk iphoneos libtool -static -o "$objdir/libspektralab_engine.a" "${objs[@]}" 2>/dev/null
}

cxx=$(xcrun --sdk iphoneos --find clang++)

build_slice "$out_dev/obj" arm64-apple-ios${IOS_MIN} "$sdk_dev"
cp "$out_dev/obj/libspektralab_engine.a" "$out_dev/libspektralab_engine.a"
build_slice "$out_sim/obj" arm64-apple-ios${IOS_MIN}-simulator "$sdk_sim"
cp "$out_sim/obj/libspektralab_engine.a" "$out_sim/libspektralab_engine.a"
echo "static lib  -> $out_dev/libspektralab_engine.a ($(lipo -info "$out_dev/libspektralab_engine.a" 2>&1 | sed 's/.*: //'))"
echo "static lib  -> $out_sim/libspektralab_engine.a ($(lipo -info "$out_sim/libspektralab_engine.a" 2>&1 | sed 's/.*: //'))"

# The kernels: iOS 18 metal, safe math (the two flags engine/build.sh calls load-bearing).
airs=()
for m in "$eng"/src/shaders/*.metal; do
  a="$out_dev/air/$(basename "$m" .metal).air"
  xcrun -sdk iphoneos metal -fmetal-math-mode=safe -fmetal-math-fp32-functions=precise \
    -c -target air64-apple-ios${IOS_MIN} -Werror "$m" -o "$a"
  airs+=("$a")
done

res="$out_dev/EngineResources"
mkdir -p "$res"
rsync -a --exclude '*.metallib' --exclude '*.metalar' "$eng/resources/" "$res/"
if [[ -d "$eng/resources_product/profiles" ]]; then
  cp "$eng/resources_product/profiles/"*.json "$res/profiles/"
  cp "$eng/resources_product/NOTICE.md" "$res/PRODUCT_PROFILES_NOTICE.md"
fi
cp "$root/license/SPEKTRAFILM_LICENSE.txt" "$res/LICENSE-PROFILES.txt"   # the CC BY-SA 4.0 notice of the profiles
xcrun -sdk iphoneos metallib "${airs[@]}" -o "$res/spektralab.metallib"
git -C "$root" log -1 --format='%h %cs' -- engine > "$res/ENGINE-COMMIT.txt"

# The stamp read back, as engine/build.sh does: the metallib's platform must be the floor the
# app declares, or older devices open the app to a render that never comes. metal-readobj not
# printing a platform at all is said loudly and let go -- the check fires where the answer exists.
major=$(xcrun -sdk iphoneos metal-readobj --file-headers "$res/spektralab.metallib" \
          | awk '/PlatformMajor:/ {print $2; exit}')
if [[ -n "$major" && "$major" != "${IOS_MIN%%.*}" ]]; then
  echo "build_engine_ios.sh: the metallib targets iOS $major, not $IOS_MIN -- it would not load on the floor devices" >&2
  exit 1
elif [[ -z "$major" ]]; then
  echo "build_engine_ios.sh: metal-readobj named no PlatformMajor; the stamp went unchecked" >&2
fi

# The optional native archive: baked by a host tool from the metallib just made. Then the whole
# resources folder is laid into the simulator's too (the simulators read the device's metallib).
"$eng/tools/build_metal_archive.sh" "$res/spektralab.metallib" "$res/spektralab.metalar" "$out_dev"
rsync -a "$res/" "$out_sim/EngineResources/"
echo "resources   -> $res ($(du -sh "$res" | cut -f1)) and $out_sim/EngineResources, engine $(cat "$res/ENGINE-COMMIT.txt")"
