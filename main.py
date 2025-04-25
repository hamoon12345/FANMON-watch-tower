#!/usr/bin/env python3
"""
SECURITY WATCHTOWER - Centralized Monitoring System
Version: 2.1.0
"""
#!/usr/bin/env python3
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from time import sleep
import os
import subprocess
import sys
import time
from colorama import Fore , Back , Style
from threading import Thread
import os
import subprocess
import sys
import time
from threading import Thread
import logging
import os
import sys
import time
import signal
import logging
import subprocess
from pathlib import Path
from typing import Dict, List
from threading import Thread, Event
from datetime import datetime
red = Fore.LIGHTRED_EX; green = Fore.LIGHTGREEN_EX; blue = Fore.LIGHTBLUE_EX; yellow = Fore.LIGHTYELLOW_EX; cyan = Fore.LIGHTCYAN_EX; white = Fore.LIGHTWHITE_EX; magenta = Fore.LIGHTMAGENTA_EX;
# Rich console for beautiful output
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress
from rich.logging import RichHandler
from rich.table import Table
from rich.style import Style

os.system("clear")

# Configuration
class Config:
    SCRIPT_DIR = Path("modules")
    LOG_DIR = Path("logs")
    RESTART_DELAY = 60
    MAX_RESTARTS = 5
    
    MONITORS = {
        "ssl": {
            "script": "sslcertwatch.py",
            "description": "SSL Certificate Monitor"
        },
        "medium": {
            "script": "medium.py",
            "description": "medium write up watcher"
        },
        "ports": {
            "script": "openpo.py",
            "description": "Port Scanner"
        },
        "params": {
            "script": "paramwatch.py",
            "description": "Parameter Monitor"
        },
        "javascript": {
            "script": "jsw.py",
            "description": "JS File Tracker"
        },
        "subdomains": {
            "script": "subwatcher.py",
            "description": "Subdomain Discovery"
        }
    }

# Setup logging
os.makedirs(Config.LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        RichHandler(show_time=False, rich_tracebacks=True),
        logging.FileHandler(Config.LOG_DIR / "watchtower.log")
    ]
)
log = logging.getLogger("watchtower")

class ProcessManager:
    """Manages monitoring processes with restart capabilities"""
    
    def __init__(self):
        self.console = Console()
        self.processes: Dict[str, subprocess.Popen] = {}
        self.restart_counts: Dict[str, int] = {}
        self.shutdown_event = Event()
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.console.print("\n[red]Shutdown signal received[/]")
        self.shutdown_event.set()

    def _log_stream(self, stream, logger):
        """Log process output in real-time"""
        for line in iter(stream.readline, ''):
            logger(line.strip())
        stream.close()

    def run_monitor(self, script: str, description: str):
        """Run a monitoring script with supervision"""
        script_path = Config.SCRIPT_DIR / script
        
        while not self.shutdown_event.is_set():
            try:
                self.console.print(f"[bold green]STARTING[/] {description} ({script})")
                
                proc = subprocess.Popen(
                    [sys.executable, str(script_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
                self.processes[script] = proc
                
                # Start output logging threads
                Thread(
                    target=self._log_stream,
                    args=(proc.stdout, lambda msg: log.info(f"[{script}] {msg}")),
                    daemon=True
                ).start()
                
                Thread(
                    target=self._log_stream,
                    args=(proc.stderr, lambda msg: log.error(f"[{script}] {msg}")),
                    daemon=True
                ).start()
                
                exit_code = proc.wait()
                
                if exit_code != 0:
                    self.restart_counts[script] = self.restart_counts.get(script, 0) + 1
                    if self.restart_counts[script] > Config.MAX_RESTARTS:
                        log.critical(f"Max restarts reached for {script}")
                        break
                        
                    log.warning(f"{script} exited with code {exit_code}, restarting...")
                    time.sleep(Config.RESTART_DELAY)
                
            except Exception as e:
                log.error(f"Error running {script}: {str(e)}")
                time.sleep(Config.RESTART_DELAY)

    def shutdown(self):
        """Terminate all running processes"""
        self.console.print("\n[bold yellow]Terminating monitors...[/]")
        for name, proc in self.processes.items():
            try:
                proc.terminate()
                proc.wait(timeout=5)
                self.console.print(f"  [red]×[/] Stopped {name}")
            except subprocess.TimeoutExpired:
                proc.kill()
                self.console.print(f"  [bold red]×[/] Force killed {name}")

class Watchtower:
    """Main application controller"""
    
    def __init__(self):
        self.console = Console()
        self.manager = ProcessManager()
        self.start_time = datetime.now()

    def display_banner(self):
        """Show the Watchtower banner"""
        banner_text = Text("""
███████╗ █████╗ ███╗   ██╗███╗   ███╗ ██████╗ ███╗   ██╗
██╔════╝██╔══██╗████╗  ██║████╗ ████║██╔═══██╗████╗  ██║
█████╗  ███████║██╔██╗ ██║██╔████╔██║██║   ██║██╔██╗ ██║
██╔══╝  ██╔══██║██║╚██╗██║██║╚██╔╝██║██║   ██║██║╚██╗██║
██║     ██║  ██║██║ ╚████║██║ ╚═╝ ██║╚██████╔╝██║ ╚████║
╚═╝     ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝
""", style="bold blue")
        
        self.console.print(Panel(
            banner_text,
            title="[bold red]Security Watchtower[/]",
            subtitle=f"[italic]v1.0[/] [dim]| {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}[/]",
            border_style="blue"
        ))

    def show_disclaimer(self):
        """Display legal disclaimer with acknowledgment"""
        disclaimer = Panel.fit(
            Text("\n⚠️  LEGAL NOTICE ⚠️\n\n"
                 "This software is provided strictly for:\n"
                 "  • Authorized security testing\n"
                 "  • Educationa purposes\n"
                 "  • Defensive security operations\n\n"
                 "Unauthorized use against any system without explicit permission is illegal.\n"
                 "By continuing, you affirm you have proper authorization for all monitored targets."),
            title="Terms of Use",
            border_style="red"
        )
        
        self.console.print(disclaimer)
        
        # Require explicit acknowledgment
        try:
            inuy = input(Fore.LIGHTBLUE_EX+" ┌─["+Fore.LIGHTRED_EX+"FANMON"+Fore.BLUE+"~"+Fore.WHITE+"@ROOT Press enter to run the tool or press Ctrl+c to exit the tool"+Fore.LIGHTBLUE_EX+"""]
 └──╼ """+Fore.WHITE+"> ")
        except KeyboardInterrupt:
            self.console.print("\n[red]Execution aborted by user[/]")
            sys.exit(0)

    def validate_environment(self) -> bool:
        """Verify all requirements are met"""
        checks = Table(title="Environment Validation", style="blue")
        checks.add_column("Check", style="cyan")
        checks.add_column("Status", style="magenta")
        
        # Verify Python version
        py_version = sys.version_info
        if py_version >= (3, 8):
            checks.add_row("Python ≥ 3.8", "✓")
        else:
            checks.add_row("Python ≥ 3.8", f"✖ (Found {py_version.major}.{py_version.minor})")
            return False
            
        # Verify script directory
        if Config.SCRIPT_DIR.exists():
            checks.add_row("Scripts directory", "✓")
        else:
            checks.add_row("Scripts directory", f"✖ (Missing: {Config.SCRIPT_DIR})")
            return False
            
        # Verify individual scripts
        all_valid = True
        for name, config in Config.MONITORS.items():
            script = Config.SCRIPT_DIR / config["script"]
            if script.exists():
                checks.add_row(f"{config['description']}", "✓")
            else:
                checks.add_row(f"{config['description']}", f"✖ (Missing: {script})")
                all_valid = False
                
        self.console.print(checks)
        return all_valid

    def display_status(self):
        """Show real-time monitoring dashboard"""
        status = Table(title="Active Monitors", style="green")
        status.add_column("Monitor", style="cyan")
        status.add_column("PID", style="magenta")
        status.add_column("Status", style="yellow")
        status.add_column("Restarts", style="blue")
        
        for name, proc in self.manager.processes.items():
            status.add_row(
                Config.MONITORS[name]["description"],
                str(proc.pid),
                "[green]Running[/]" if proc.poll() is None else "[red]Stopped[/]",
                str(self.manager.restart_counts.get(name, 0)))
                
        self.console.print(status)

    def run(self):
        """Main execution flow"""
        try:
            self.display_banner()
            self.show_disclaimer()
            
            if not self.validate_environment():
                self.console.print("[bold red]Failed environment validation[/]")
                sys.exit(1)
                
            # Start all monitors
            for name, config in Config.MONITORS.items():
                Thread(
                    target=self.manager.run_monitor,
                    args=(config["script"], config["description"]),
                    daemon=True
                ).start()
                
            # Main loop
            while not self.manager.shutdown_event.is_set():
                os.system('clear')
                self.display_banner()
                self.display_status()
                self.console.print("\n[dim]Press Ctrl+C to shutdown gracefully...[/]")
                time.sleep(5)
                
        except Exception as e:
            log.critical(f"Fatal error: {str(e)}", exc_info=True)
            self.console.print(f"[bold red]CRITICAL ERROR:[/] {str(e)}")
        finally:
            self.manager.shutdown()
            runtime = datetime.now() - self.start_time
            self.console.print(f"\n[bold]Runtime:[/] {runtime}\n")

if __name__ == "__main__":
    Watchtower().run()