[app]
title = Pixel Survival
package.name = pixelsurvival
package.domain = org.yourname

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,otf,wav,ogg

version = 1.0
requirements = python3==3.10.12,hostpython3==3.10.12,pygame

# 横屏游戏
orientation = landscape
fullscreen = 1

# Android 权限：本游戏不需要联网/存储，留空即可
android.permissions =

# API / NDK：用 buildozer 默认值即可，不用手动改
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a

# 图标（可选，放一张 512x512 png 到项目根目录后取消下面注释）
# icon.filename = %(source.dir)s/icon.png

[buildozer]
log_level = 2
warn_on_root = 1
