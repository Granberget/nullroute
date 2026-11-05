"""EXAMPLES and SEE ALSO sections for man pages.

Example lines starting at column 0 are commands (highlighted); indented
lines explain them.
"""

EXAMPLES: dict[str, str] = {
    "ls": """
ls -la
    every file, including hidden ones (starting with .), with details
ls -lh /var/log
    details with human readable sizes (4.0K, 1.2M)
ls -lt
    newest files first
ls *.txt
    only names ending in .txt (the shell expands the *)
ls | wc -l
    count the entries in this directory
""",
    "cd": """
cd /var/log
    go to an absolute path
cd ..
    go up one level
cd
    go home (same as cd ~)
cd -
    go back to the previous directory
""",
    "pwd": """
pwd
    print where you are, e.g. /home/neo/contracts
""",
    "cat": """
cat notes.txt
    print a file
cat a.txt b.txt > both.txt
    concatenate two files into a third
grep -n '' file
    print a file with line numbers
""",
    "less": """
less /var/log/syslog
    page through a long file (here it prints like cat)
""",
    "head": """
head file
    first 10 lines
head -n 3 file
    first 3 lines
ls -t | head -5
    the five most recently changed files
""",
    "tail": """
tail -n 20 /var/log/syslog
    the last 20 lines
tail -f /var/log/syslog
    keep following the file; Ctrl+C stops
tail -f /var/log/syslog &
    follow it in the background while you keep working (kill %1 stops it)
""",
    "grep": """
grep error app.log
    lines containing 'error'
grep -i error app.log
    ...ignoring upper/lower case
grep -rn passphrase /home
    search every file under /home, show file names and line numbers
grep -rl falcon .
    only list the files that match
grep -v '^#' config
    lines that do NOT start with #
grep -c GET access.log
    count matching lines
ps aux | grep nginx
    filter another command's output
""",
    "find": """
find . -name '*.txt'
    every .txt file below the current directory (quote the pattern!)
find / -name '*.dat' 2>/dev/null
    search everything, hide 'Permission denied' errors
find /data -type d
    only directories
find ~ -iname 'readme*'
    case-insensitive name match
find /var/log -name '*.log' | wc -l
    count them
""",
    "cp": """
cp a.txt b.txt
    copy a file
cp a.txt docs/
    copy into a directory, keeping the name
cp -r project project.bak
    copy a whole directory
""",
    "mv": """
mv old.txt new.txt
    rename
mv *.log logs/
    move many files into a directory
""",
    "rm": """
rm file.txt
    delete a file (no undo, no trash can)
rm -r olddir
    delete a directory and everything in it
rm -i *.tmp
    ask before each file
""",
    "mkdir": """
mkdir notes
    create one directory
mkdir -p projects/2031/q1
    create the whole path, including missing parents
""",
    "touch": """
touch notes.txt
    create an empty file (or update the time of an existing one)
""",
    "echo": """
echo hello
    print text
echo "export PATH" >> ~/.bashrc
    append a line to a file
echo $HOME
    print a variable
""",
    "wc": """
wc -l file
    count lines
ls | wc -l
    count files
grep -r TODO . | wc -l
    count matches across many files
""",
    "sort": """
sort names.txt
    alphabetical
sort -n numbers.txt
    numerical (so 10 comes after 9)
sort -rn
    largest first
sort file | uniq -c | sort -rn | head
    the most common lines - a classic!
""",
    "uniq": """
sort file | uniq
    remove duplicates (uniq only sees neighbours, so sort first)
sort file | uniq -c
    count how often each line appears
sort file | uniq -d
    only lines that appear more than once
""",
    "du": """
du -sh *
    size of everything in this directory
du -sh /var/log
    total size of one directory
""",
    "df": """
df -h
    free space on your disks
""",
    "tree": """
tree
    draw the directory tree below here
tree /data
    ...below another directory
""",
    "nano": """
nano notes.txt
    edit (or create) a file
nano +25 config.txt
    open with the cursor on line 25
sudo nano /etc/hosts
    edit a file that belongs to root
""",
    "ssh": """
ssh blackrelay.net
    open the agency BBS
ssh intra.acme.corp
    log in to a breached node (follows your route)
exit
    close the connection again
""",
    "scp": """
scp file.dat drop.blackrelay.net:/drop/C001/
    upload to the drop box
scp gateway:~/contracts/C002/x.dat /data/
    pull a file from your gateway (run on the target)
scp -r intra.acme.corp:/data/projects ~/downloads/
    copy a whole directory home
""",
    "sudo": """
sudo apt install cowsay
    install a package as root
sudo !!
    you forgot sudo? repeat the last command with it
sudo nano /etc/hosts
    edit a root-owned file
echo 127.0.0.1 test | sudo tee -a /etc/hosts
    append to a root-owned file (a plain > would fail)
sudo -l
    what may I do?
""",
    "su": """
sudo -i
    the right way to get a root shell on this system
""",
    "passwd": """
passwd
    change your password (sudo asks for this one)
""",
    "id": """
id
    your user ID and the groups you are in
""",
    "chmod": """
chmod +x script.sh
    make a file executable
chmod 600 secret.txt
    only you may read and write it
chmod 755 tool
    everyone may run it, only you may change it
chmod -R go-w project
    remove write rights for group and others, recursively
""",
    "chown": """
sudo chown neo file
    give a file to the user neo
sudo chown -R neo:neo dir
    owner and group for a whole tree
""",
    "stat": """
stat file
    size, permissions (both styles), owner and modification time
""",
    "tee": """
ls | tee list.txt
    show the output AND save it
echo hi | sudo tee /etc/motd
    write to a root-owned file
ls -la /etc 2>&1 | tee listing.txt
    keep a copy of everything a command prints, errors included
""",
    "which": """
which nano
    where does the nano program live?
""",
    "apt": """
sudo apt update
    refresh the package lists (do this after buying in the store)
sudo apt install cowsay
    install a package
sudo apt upgrade
    upgrade everything that has a newer version
apt search cow
    find packages by name or description
apt list --installed
    what is installed
sudo apt remove sl
    uninstall
""",
    "nmap": """
nmap osaka.relay
    which ports are open
nmap -sV intra.acme.corp
    ...and which software answers on them
nmap -p 22,80,443 intra.acme.corp
    only check these ports
nmap -sn osaka.relay tallinn.relay
    just: are these hosts up?
""",
    "mail": """
mail
    open your inbox (r reply, c compose)
echo 'all done' | mail client@quietmail.net
    send a short mail
mail -A ~/downloads/report.dat client@quietmail.net
    send a file as an attachment (type the text, end with a '.' line)
""",
    "split": """
split
    open a second terminal (same as Ctrl+N)
""",
    "ping": """
ping -c 4 osaka.relay
    four pings, then a summary
ping osaka.relay
    keep pinging until Ctrl+C
""",
    "traceroute": """
traceroute sandbox.blackrelay.net
    the hops between you and the target
""",
    "host": """
host osaka.relay
    name -> IP address
host 8.8.8.8
    IP address -> name (reverse lookup)
""",
    "dig": """
dig osaka.relay
    full DNS answer
dig +short osaka.relay
    just the address
""",
    "ip": """
ip a
    your network interfaces and addresses
ip route
    where your traffic goes by default
""",
    "ps": """
ps
    processes in this terminal
ps aux
    every process on the system
ps aux | grep sleep
    find a particular one
""",
    "kill": """
kill 4123
    ask process 4123 to stop
kill -9 4123
    force it
kill %1
    stop background job 1
""",
    "jobs": """
sleep 300 &
    start a job in the background
jobs
    list jobs
fg %1
    bring job 1 back to the foreground (Ctrl+C stops it)
""",
    "fg": """
fg
    bring the most recent job back
fg %2
    bring job 2 back
""",
    "top": """
top
    live process list; q quits, M sorts by memory, k kills
""",
    "journalctl": """
journalctl -n 20
    the last 20 lines of the system log
journalctl -f
    follow it live
journalctl -u CRON
    only lines from one service
""",
    "sleep": """
sleep 5
    wait five seconds
sleep 600 &
    a harmless background job to practise ps/kill on
sleep 2h
    fast-forward the game clock two hours (gateway only)
""",
    "man": """
man grep
    the manual for grep
man man
    you are here
""",
    "history": """
history
    numbered list of earlier commands
!!
    run the last command again
sudo !!
    ...as root
""",
    "breach": """
breach intra.acme.corp
    run your breach programs against the node's ICE
""",
    "probe": """
probe core.acme.corp
    what protects this node, and can I break it?
""",
    "hydra": """
hydra -l admin -P /usr/share/wordlists/common.txt intra.acme.corp ssh
    try the login 'admin' against ssh with a whole password list
hydra -L /usr/share/wordlists/users.txt -P /usr/share/wordlists/common.txt ssh://intra.acme.corp
    try many logins too (service://host form)
hydra -l root -p hunter2 intra.acme.corp ssh
    try a single login/password guess
hydra -f -L users.txt -P common.txt intra.acme.corp ssh
    stop at the first login that works
    (breach the node first - a filtered port can't be brute-forced)
""",
    "route": """
route add osaka
    add a relay to your bounce route
route del 1
    remove the first hop
route
    show the route
""",
    "learn": """
learn
    list the lessons
learn 1
    start lesson 1
learn check
    check your work
""",
}

SEE_ALSO: dict[str, list[str]] = {
    "ls": ["cd", "tree", "stat", "find"], "cd": ["pwd", "ls"], "cat": ["less", "head", "tail"],
    "head": ["tail", "less"], "tail": ["head", "journalctl"], "grep": ["find", "sort", "wc"],
    "find": ["grep", "ls"], "cp": ["mv", "scp"], "mv": ["cp", "rm"], "rm": ["rmdir", "mv"],
    "sort": ["uniq", "wc"], "uniq": ["sort"], "chmod": ["chown", "ls", "stat"],
    "chown": ["chmod", "chgrp"], "sudo": ["su", "passwd", "id"], "apt": ["dpkg", "sudo"],
    "ps": ["top", "kill", "pgrep"], "kill": ["ps", "jobs", "killall"], "jobs": ["fg", "bg", "kill"],
    "ping": ["traceroute", "host"], "host": ["dig", "nslookup"], "dig": ["host", "nslookup"],
    "traceroute": ["ping", "route"], "tee": ["sudo"], "nano": ["cat", "less"],
    "hydra": ["breach", "probe", "nmap", "scrub"], "breach": ["probe", "hydra", "ssh"],
    "nmap": ["hydra", "probe", "ping"],
}
