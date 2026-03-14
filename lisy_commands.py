#!/data/data/com.termux/files/usr/bin/env python3
"""
LISY - Bidirectional Folder Synchronization System
Complete implementation for Termux environment
"""

import os
import sys
import json
import time
import shutil
import hashlib
import fcntl
import signal
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

class LISYCore:
    """Core LISY functionality"""

    def __init__(self):
        self.home = Path(os.environ.get('HOME', '/data/data/com.termux/files/home'))
        self.lisy_dir = self.home / 'LISY'
        self.db_file = self.lisy_dir / 'database'
        self.locks_dir = self.lisy_dir / 'locks'
        self.runtime_dir = self.lisy_dir / 'runtime'
        self.pid_dir = self.runtime_dir / 'pids'
        self._init_structure()

    def _init_structure(self):
        for dir_path in [self.lisy_dir, self.locks_dir, self.runtime_dir, self.pid_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        if not self.db_file.exists():
            self._save_database({})

    def _load_database(self) -> Dict:
        try:
            if self.db_file.exists():
                with open(self.db_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}

    def _save_database(self, data: Dict):
        temp_file = self.db_file.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            json.dump(data, f, indent=2)
        temp_file.replace(self.db_file)

    def _generate_link_id(self, source: str, dest: str) -> str:
        content = f"{source}:{dest}:{time.time()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _get_lock_file(self, link_id: str) -> Path:
        return self.locks_dir / f"{link_id}.lock"

    def _get_pid_file(self, link_id: str) -> Path:
        return self.pid_dir / f"{link_id}.pid"

    def _acquire_sync_lock(self, link_id: str) -> Optional[int]:
        lock_file = self._get_lock_file(link_id)
        try:
            fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except:
            return None

    def _release_sync_lock(self, fd: int, link_id: str):
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            lock_file = self._get_lock_file(link_id)
            if lock_file.exists():
                lock_file.unlink()
        except:
            pass

    def _is_process_running(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except:
            return False

    def _stop_monitor(self, link_id: str):
        pid_file = self._get_pid_file(link_id)
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                if self._is_process_running(pid):
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(0.5)
                    if self._is_process_running(pid):
                        os.kill(pid, signal.SIGKILL)
            except:
                pass
            finally:
                pid_file.unlink(missing_ok=True)
        self._get_lock_file(link_id).unlink(missing_ok=True)


class LISYCommand(LISYCore):
    def run(self):
        print("\n=== LISY - Create New Link ===\n")
        source = input("Source path: ").strip()
        if not source:
            print("Error: No source path provided.")
            return

        source_path = Path(source).expanduser().resolve()
        if not source_path.exists():
            print(f"Error: Source path does not exist: {source_path}")
            return
        if not source_path.is_dir():
            print(f"Error: Source path is not a directory: {source_path}")
            return

        folder_name = source_path.name
        dest_path = self.home / folder_name

        print(f"\nSource: {source_path}")
        print(f"Destination: {dest_path}")

        if not dest_path.exists():
            dest_path.mkdir(parents=True)
            print(f"Created destination folder.")

        db = self._load_database()
        for link_id, link_data in db.items():
            if link_data['source'] == str(source_path) or link_data['destination'] == str(dest_path):
                print(f"Error: Link already exists!")
                return

        print("\nScanning for node_modules...")
        node_modules_found = list(source_path.rglob('node_modules'))

        node_modules_allowed = False
        if node_modules_found:
            print(f"Found {len(node_modules_found)} node_modules directories.")
            choice = input("\nDo you want to include node_modules in synchronization? (y/n): ").strip().lower()
            node_modules_allowed = choice == 'y'
        else:
            print("No node_modules found.")

        print("\nPerforming initial synchronization...")
        link_id = self._generate_link_id(str(source_path), str(dest_path))

        if self._initial_sync(source_path, dest_path, node_modules_allowed, link_id):
            print("Initial synchronization complete.")
        else:
            print("Initial synchronization failed.")
            return

        timestamp = datetime.now().isoformat()
        db[link_id] = {
            'source': str(source_path),
            'destination': str(dest_path),
            'timestamp': timestamp,
            'node_modules_allowed': node_modules_allowed,
            'active': True
        }
        self._save_database(db)

        print(f"\nLink created successfully!")
        print(f"Link ID: {link_id}")
        print(f"node_modules sync: {'enabled' if node_modules_allowed else 'disabled'}")
        print("\nStarting file monitoring...")
        self._start_monitoring(link_id, source_path, dest_path, node_modules_allowed)
        print("Monitoring active. Use 'rlisy' to unlink.")

    def _should_ignore(self, path: Path, node_modules_allowed: bool) -> bool:
        name = path.name
        if name.startswith('.') or name.startswith('~') or name.endswith('~'):
            return True
        if name.endswith(('.tmp', '.temp', '.swp')):
            return True
        if name in ['.DS_Store', 'Thumbs.db']:
            return True
        if 'node_modules' in str(path) and not node_modules_allowed:
            return True
        return False

    def _initial_sync(self, source: Path, dest: Path, node_modules_allowed: bool, link_id: str) -> bool:
        try:
            lock_fd = self._acquire_sync_lock(link_id)
            self._sync_directories(source, dest, node_modules_allowed)
            self._sync_directories(dest, source, node_modules_allowed)
            if lock_fd:
                self._release_sync_lock(lock_fd, link_id)
            return True
        except Exception as e:
            print(f"Sync error: {e}")
            return False

    def _sync_directories(self, src: Path, dst: Path, node_modules_allowed: bool):
        for item in src.rglob('*'):
            if self._should_ignore(item, node_modules_allowed):
                continue
            rel_path = item.relative_to(src)
            dst_item = dst / rel_path
            if item.is_file():
                if not dst_item.exists() or item.stat().st_mtime > dst_item.stat().st_mtime:
                    dst_item.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dst_item)
            elif item.is_dir():
                dst_item.mkdir(parents=True, exist_ok=True)

    def _start_monitoring(self, link_id: str, source: Path, dest: Path, node_modules_allowed: bool):
        monitor_script = self.runtime_dir / f"monitor_{link_id}.py"
        script_content = f"""
import sys
sys.path.insert(0, '{self.lisy_dir}')
from lisy_daemon import MonitorDaemon
MonitorDaemon('{link_id}', '{source}', '{dest}', {node_modules_allowed}).run()
"""
        monitor_script.write_text(script_content)
        process = subprocess.Popen(
            [sys.executable, str(monitor_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        self._get_pid_file(link_id).write_text(str(process.pid))


class LISYNCommand(LISYCore):
    def run(self):
        print("\n=== LISYN - Node Modules Manager ===\n")
        db = self._load_database()
        if not db:
            print("No active links found.")
            return

        print("Menu:")
        print("[1] Add node_modules synchronization")
        print("[2] Remove node_modules synchronization")
        print("[0] Cancel")

        choice = input("\nSelect option: ").strip()

        if choice == '1':
            self._add_node_modules(db)
        elif choice == '2':
            self._remove_node_modules(db)
        else:
            print("Cancelled.")

    def _add_node_modules(self, db: Dict):
        active_links = [lid for lid, data in db.items() if data.get('active', False)]
        if not active_links:
            print("No active links found.")
            return

        print("\nActive links:")
        for i, link_id in enumerate(active_links, 1):
            data = db[link_id]
            print(f"[{i}] {Path(data['source']).name}")

        try:
            selection = int(input("\nSelect link: ").strip()) - 1
            if selection < 0 or selection >= len(active_links):
                print("Invalid selection.")
                return
        except ValueError:
            print("Invalid input.")
            return

        link_id = active_links[selection]
        db[link_id]['node_modules_allowed'] = True
        self._save_database(db)
        print(f"\nnode_modules synchronization enabled for {Path(db[link_id]['source']).name}")

    def _remove_node_modules(self, db: Dict):
        nm_links = [(lid, data) for lid, data in db.items() 
                    if data.get('active', False) and data.get('node_modules_allowed', False)]

        if not nm_links:
            print("No links with node_modules synchronization found.")
            return

        print("\nLinks with node_modules sync:")
        for i, (link_id, data) in enumerate(nm_links, 1):
            print(f"[{i}] {Path(data['source']).name}")

        try:
            selection = int(input("\nSelect link: ").strip()) - 1
            if selection < 0 or selection >= len(nm_links):
                print("Invalid selection.")
                return
        except ValueError:
            print("Invalid input.")
            return

        link_id, data = nm_links[selection]
        db[link_id]['node_modules_allowed'] = False
        self._save_database(db)
        print(f"\nnode_modules synchronization disabled for {Path(data['source']).name}")

        delete_choice = input("\nDo you want to delete node_modules folders? (y/n): ").strip().lower()
        if delete_choice == 'y':
            self._handle_deletion(data)

    def _handle_deletion(self, data: Dict):
        print("\nWhere to delete node_modules from?")
        print("[1] Source folder")
        print("[2] Termux folder")
        print("[3] Both folders")
        print("[0] Cancel")

        choice = input("\nSelect: ").strip()
        if choice == '0':
            return

        if choice in ['2', '3']:
            print("\n⚠️  WARNING:")
            print("Deleting node_modules from the Termux folder may stop your server")
            print("or development environment. You may need to run 'npm install' again")
            print("to restore dependencies.")
            confirm = input("\nDo you want to proceed? (yes/no): ").strip().lower()
            if confirm != 'yes':
                print("Deletion cancelled.")
                return

        source = Path(data['source'])
        dest = Path(data['destination'])
        deleted_count = 0

        if choice in ['1', '3']:
            deleted_count += self._delete_node_modules(source)
        if choice in ['2', '3']:
            deleted_count += self._delete_node_modules(dest)

        print(f"\nDeleted {deleted_count} node_modules directories.")

    def _delete_node_modules(self, path: Path) -> int:
        count = 0
        try:
            for nm_dir in path.rglob('node_modules'):
                if nm_dir.is_dir():
                    shutil.rmtree(nm_dir)
                    count += 1
        except:
            pass
        return count


class RLISYCommand(LISYCore):
    def run(self):
        print("\n=== RLISY - Unlink Folders ===\n")
        db = self._load_database()
        if not db:
            print("No active links found.")
            return

        active_links = [(lid, data) for lid, data in db.items() if data.get('active', False)]
        if not active_links:
            print("No active links found.")
            return

        print("Active links:")
        for i, (link_id, data) in enumerate(active_links, 1):
            source_name = Path(data['source']).name
            print(f"\n[{i}] {source_name}")
            print(f"    Source: {data['source']}")
            print(f"    Destination: {data['destination']}")

        try:
            selection = input("\nSelect link to unlink (number or 'all'): ").strip()

            if selection.lower() == 'all':
                for link_id, _ in active_links:
                    self._unlink(link_id, db)
                print("\nAll links removed.")
            else:
                idx = int(selection) - 1
                if idx < 0 or idx >= len(active_links):
                    print("Invalid selection.")
                    return
                link_id, data = active_links[idx]
                self._unlink(link_id, db)
                print(f"\nLink '{Path(data['source']).name}' unlinked successfully.")
        except ValueError:
            print("Invalid input.")

    def _unlink(self, link_id: str, db: Dict):
        self._stop_monitor(link_id)
        self._get_lock_file(link_id).unlink(missing_ok=True)
        if link_id in db:
            del db[link_id]
        self._save_database(db)
        monitor_script = self.runtime_dir / f"monitor_{link_id}.py"
        monitor_script.unlink(missing_ok=True)
        pid_file = self._get_pid_file(link_id)
        pid_file.unlink(missing_ok=True)


class LISYResumeCommand(LISYCore):
    def run(self):
        print("\n=== LISY Resume - Database Refresh ===\n")
        db = self._load_database()
        if not db:
            print("No links in database.")
            return

        valid_links = []
        broken_links = []

        for link_id, data in list(db.items()):
            source = Path(data['source'])
            dest = Path(data['destination'])
            if source.exists() and dest.exists():
                valid_links.append((link_id, data))
            else:
                broken_links.append(link_id)
                print(f"⚠️  Broken link detected: {source.name}")

        for link_id in broken_links:
            self._stop_monitor(link_id)
            if link_id in db:
                del db[link_id]

        if broken_links:
            self._save_database(db)
            print(f"\nRemoved {len(broken_links)} broken link(s).")

        print(f"\nRestarting monitoring for {len(valid_links)} valid link(s)...")
        for link_id, data in valid_links:
            self._stop_monitor(link_id)
            source = Path(data['source'])
            dest = Path(data['destination'])
            nm_allowed = data.get('node_modules_allowed', False)
            self._start_monitoring(link_id, source, dest, nm_allowed)
            print(f"  ✓ {source.name}")
        print("\nResume complete.")

    def _start_monitoring(self, link_id: str, source: Path, dest: Path, node_modules_allowed: bool):
        monitor_script = self.runtime_dir / f"monitor_{link_id}.py"
        script_content = f"""
import sys
sys.path.insert(0, '{self.lisy_dir}')
from lisy_daemon import MonitorDaemon
MonitorDaemon('{link_id}', '{source}', '{dest}', {node_modules_allowed}).run()
"""
        monitor_script.write_text(script_content)
        process = subprocess.Popen(
            [sys.executable, str(monitor_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        self._get_pid_file(link_id).write_text(str(process.pid))


def main():
    if len(sys.argv) < 1:
        print("Usage: lisy [resume]|lisyn|rlisy")
        return

    cmd = sys.argv[0]
    args = sys.argv[1:]

    if 'rlisy' in cmd:
        RLISYCommand().run()
    elif 'lisyn' in cmd:
        LISYNCommand().run()
    elif 'lisy' in cmd:
        if args and args[0] == 'resume':
            LISYResumeCommand().run()
        else:
            LISYCommand().run()
    else:
        print("Unknown command. Use: lisy, lisyn, or rlisy")

if __name__ == '__main__':
    main()
