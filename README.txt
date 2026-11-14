NEON//PHANTOM v1.0 - Advanced Fake Hacker Terminal Simulator
==============================================================

এটি সম্পূর্ণ বিনোদনমূলক Visual Simulation।
This is an entertainment-only visual simulation.

কোনো বাস্তব নেটওয়ার্ক, Wi-Fi, IP, Camera, Mic, GPS, Location বা ফাইল সিস্টেম
অ্যাক্সেস করা হয় না। সব IP, GPS, CPU, RAM ও Network ডেটা কাল্পনিক (random)।
Fake IP গুলো শুধু documentation/private range থেকে আসে
(192.0.2.x, 198.51.100.x, 203.0.113.x, 10.x, 172.16.x, 192.168.x)।

প্রোগ্রাম শুধু একটি ছোট settings ফাইল লেখে: ~/.neon_phantom.json
(username, sound, speed)। মুছে ফেললে কোনো সমস্যা নেই।


--------------------------------------------------------------
1) Termux-এ Installation (ধাপে ধাপে)
--------------------------------------------------------------

ধাপ 1: Termux ইনস্টল করুন (F-Droid থেকে নেওয়া ভালো)।

ধাপ 2: Termux খুলে প্যাকেজ আপডেট করুন:

    pkg update -y && pkg upgrade -y

ধাপ 3: Python ইনস্টল করুন:

    pkg install python -y

ধাপ 4 (ফাইল ফোনের Download ফোল্ডারে থাকলে): Storage permission দিন:

    termux-setup-storage

ধাপ 5: ফাইল Termux home-এ কপি করুন:

    cp ~/storage/downloads/neon_phantom.py ~/
    cp ~/storage/downloads/README.txt ~/

(ফাইল অন্য ফোল্ডারে থাকলে পথ বদলে নিন।)


--------------------------------------------------------------
2) Running (চালানোর নিয়ম)
--------------------------------------------------------------

    cd ~
    python neon_phantom.py

বা executable বানিয়ে:

    chmod +x neon_phantom.py
    ./neon_phantom.py

প্রথমবার চালালে আপনার Hacker Username জিজ্ঞেস করবে।
পরে Settings (মেনু 22) থেকে বদলানো যাবে।


--------------------------------------------------------------
3) ব্যবহার
--------------------------------------------------------------

Main Menu
  1  Automatic Hacker Mode  - নিজে থেকে একটার পর একটা animation চলবে,
                              কখনো থামবে না। Ctrl+C = Main Menu-তে ফেরা।
  2  Command Console        - নিচে কমান্ড তালিকা দেখুন।
  3  Matrix Code Rain       - (Ctrl+C দিলে বন্ধ)
  4  IP Address Scanner     - fake
  5  Port Scanner           - fake
  6  Password Decryption    - fake
  7  Firewall Bypass        - fake
  8  System Breach          - fake
  9  Database Download      - fake
  10 Satellite Connection   - fake
  11 GPS Tracking           - fake coordinates + radar
  12 CPU / RAM Monitor      - random numbers
  13 Network Traffic        - random numbers
  14 Hash Generator         - random বা আপনার লেখা text-এর hash
  15 Encrypt / Decrypt      - toy XOR cipher (শুধু দেখানোর জন্য)
  16 Security Alert
  17 Access Granted
  18 Mission Complete       - session stats সহ
  19 Random Hacker Commands
  20 Loading Animations
  21 RGB Effects
  22 Settings               - username, sound, animation speed
  0  Exit

Main Menu-তে Ctrl+C একবার চাপলে সতর্কবার্তা আসবে; ২ সেকেন্ডের মধ্যে
আবার চাপলে (বা 0 লিখলে) প্রোগ্রাম বন্ধ হবে।

Command Console কমান্ড
  help              সব কমান্ডের তালিকা
  scan              fake IP scan        (scan ports = port scan)
  portscan          fake port scan
  decrypt           fake password cracking
  decrypt msg       শেষ encrypt করা মেসেজ decrypt
  encrypt [text]    fake encryption
  connect [ip]      fake secure connection
  matrix            matrix rain
  gps               fake GPS tracking
  status            fake system status
  download          fake database download
  satellite, firewall, breach, monitor, traffic, hash [text],
  alert, access, mission, run, loading, rgb, auto
  whoami            username দেখাবে
  sound on|off      sound চালু/বন্ধ
  banner            logo
  clear             screen পরিষ্কার
  exit              Main Menu-তে ফেরা

যেকোনো animation চলার সময় Ctrl+C চাপলে সেটি থামবে এবং আগের মেনু/কনসোলে ফেরা যাবে।


--------------------------------------------------------------
4) Sound Effects (ঐচ্ছিক)
--------------------------------------------------------------

Standard library-তে শুধু terminal bell (\a) পাওয়া যায়। Termux-এ এটি
আপনার Termux bell সেটিং অনুযায়ী vibration বা শব্দ করতে পারে।
(Termux Settings: ~/.termux/termux.properties -> bell-character=vibrate / beep / ignore)
পছন্দ না হলে Settings (মেনু 22) বা console-এ "sound off" দিন।


--------------------------------------------------------------
5) সেরা দেখার টিপস
--------------------------------------------------------------

- Termux-এ Portrait mode-এ চালান; স্ক্রিন প্রস্থ অনুযায়ী UI নিজে adjust হয়।
- সবচেয়ে ভালো রঙের জন্য Termux আপডেট রাখুন (24-bit true color দরকার)।
- লোগো বা বক্স ভেঙে গেলে দুই আঙুলে pinch করে font ছোট করুন (প্রায় 40+ column)।
- Matrix Rain ও Monitor ভালোভাবে দেখতে ফোন landscape-এও ঘুরিয়ে দেখতে পারেন।
- Animation ধীর/দ্রুত করতে: Settings -> Animation speed (FAST / NORMAL / SLOW)।


--------------------------------------------------------------
6) সমস্যা সমাধান
--------------------------------------------------------------

* "python: command not found"       -> pkg install python
* রঙ ঠিকমতো আসছে না                 -> Termux আপডেট করুন, অন্য terminal হলে true color চালু আছে কিনা দেখুন
* অক্ষর ভেঙে যাচ্ছে (□ চিহ্ন)       -> Termux:Styling থেকে অন্য monospace font নিন
* সম্পূর্ণ বন্ধ করে ঠিক করতে        -> Termux-এ "reset" কমান্ড চালান


--------------------------------------------------------------
Requirements: Python 3.6+, শুধু standard library, কোনো pip package নয়, root নয়।
Stay legal. Stay curious. It's all a simulation.