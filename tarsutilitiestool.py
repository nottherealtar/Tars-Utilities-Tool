import os
import re
import sys
import time
import datetime
import socket
import json
import urllib.request
import psutil  # Add this for process monitoring
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich.layout import Layout
from rich.align import Align
from rich.style import Style
from rich.box import DOUBLE, ASCII
from rich.columns import Columns
from elevate import elevate
import threading
import signal
import subprocess

# Try to import keyboard handling modules based on platform
try:
    import msvcrt  # Windows
except ImportError:
    try:
        import tty
        import termios
    except ImportError:
        pass

# Add this import for Windows compatibility
try:
    import curses
except ImportError:
    import windows_curses as curses

# Add these to the import section at the top
from datetime import datetime, timedelta

# Define theme colors
HACKER_GREEN = "bright_green"
HACKER_BG = "black"
MAIN_STYLE = f"{HACKER_GREEN} on {HACKER_BG}"
HIGHLIGHT_STYLE = f"black on {HACKER_GREEN}"
BORDER_STYLE = HACKER_GREEN

# Create console with theme
console = Console(color_system="auto", highlight=False)

# Request elevated privileges
elevate()

# Set up logging directory and file
log_dir = os.path.join(os.path.expanduser("~"), "ShutdownTimer")
log_file = os.path.join(log_dir, "shutdown_log.txt")

if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Global variables to track timer state
timer_active = False
end_time = None
timer_type = None
timer_thread = None

def clear_screen():
    """Clear the screen completely and reset cursor position"""
    if os.name == 'nt':  # Windows
        os.system('cls')
    else:  # Unix/Linux/MacOS
        os.system('clear')
    # Also use Rich's console.clear which works better in some terminals
    console.clear()

def log_event(action, duration_seconds):
    """Log shutdown events to a file"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a") as f:
        f.write(f"{timestamp} | {action} | Duration: {duration_seconds} seconds\n")

def read_logs():
    """Read and return the shutdown logs"""
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            return f.readlines()
    return []

def print_banner():
    """Print a fancy ASCII banner"""
    # Clear the console before printing anything
    clear_screen()
    
    banner = Text(r"""
    ╔════════════════════════════════════════════════════════════════════════╗
    ║  _____              ____ _           _     _                           ║
    ║ |_   _|_ _ _ __ ___|  __| |_  _   _ | |_  |__ |  _____  __ __ __  __  ║
    ║   | | / _` | '__/ __| |_ | __|   | || | | | _ \  \___ \ \ \/ // / / /  ║
    ║   | || (_| | |  \__ \  _|| |_    | || | | | | | | ___) | >  <| |_| |   ║
    ║   |_| \__,_|_|  |___/_|   \__|   |_||_|_| |_| |_||____/ /_/\_\\__, |   ║
    ║                                                               |___/    ║
    ╚════════════════════════════════════════════════════════════════════════╝
    """, style=MAIN_STYLE)
    console.print(Align.center(banner))
    # Add consistent spacing after banner
    console.print()

def get_key():
    """Get a keypress from the user, cross-platform."""
    if os.name == 'nt':  # Windows
        key = msvcrt.getch()
        # Handle special keys (arrows)
        if key == b'\xe0':  # Special key prefix
            key = msvcrt.getch()
            if key == b'H':  # Up arrow
                return 'UP'
            elif key == b'P':  # Down arrow
                return 'DOWN'
            elif key == b'K':  # Left arrow
                return 'LEFT'
            elif key == b'M':  # Right arrow
                return 'RIGHT'
        elif key == b'\r':  # Enter key
            return 'ENTER'
        elif key == b'\x1b':  # Escape key
            return 'ESC'
        else:
            return key.decode('utf-8', errors='ignore')
    else:  # Unix-like
        try:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                ch = sys.stdin.read(1)
                # Handle escape sequences for arrow keys
                if ch == '\x1b':
                    ch = sys.stdin.read(1)
                    if ch == '[':
                        ch = sys.stdin.read(1)
                        if ch == 'A':
                            return 'UP'
                        elif ch == 'B':
                            return 'DOWN'
                        elif ch == 'C':
                            return 'RIGHT'
                        elif ch == 'D':
                            return 'LEFT'
                    return 'ESC'
                elif ch == '\r':
                    return 'ENTER'
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return ch
        except:
            # If we can't use termios, fall back to input()
            return input()

def arrow_menu(title, options):
    """Display a menu with arrow key navigation"""
    current_option = 0
    
    while True:
        # Use the improved clear screen function
        clear_screen()
        print_banner()
        
        # Create title with consistent spacing
        panel_title = Text(title, style=f"bold {HACKER_GREEN}")
        console.print(Align.center(panel_title))
        console.print()  # Space after title
        
        # Display menu options with consistent spacing
        for i, option in enumerate(options):
            if i == current_option:
                # Highlighted option
                text = Text(f"➤ {option}", style=HIGHLIGHT_STYLE)
            else:
                # Normal option
                text = Text(f"  {option}", style=MAIN_STYLE)
            console.print(Align.center(text))
        
        # Add space after menu options
        console.print()
        
        # Get key press
        key = get_key()
        
        if key == 'UP' and current_option > 0:
            current_option -= 1
        elif key == 'DOWN' and current_option < len(options) - 1:
            current_option += 1
        elif key == 'ENTER':
            # Clear screen immediately upon selection
            clear_screen()
            return current_option
        elif key == 'ESC':
            # Clear screen when going back
            clear_screen()
            return -1  # -1 means back/cancel

def cancel_shutdown():
    """Cancel any scheduled shutdown or restart"""
    global timer_active, end_time, timer_type, timer_thread
    
    clear_screen()
    print_banner()
    
    if timer_active:
        # First cancel the Windows shutdown command
        os.system("shutdown -a")
        log_event(f"Cancelled {timer_type}", 0)
        
        # Update global variables to signal thread termination
        timer_active = False
        end_time = None
        timer_type = None
        
        # Wait for thread to terminate
        if timer_thread and timer_thread.is_alive():
            timer_thread.join(0.5)  # Increased timeout for thread to exit cleanly
        
        console.print()  # Add space before progress bar
        
        with Progress(
            SpinnerColumn(spinner_name="dots2", style=HACKER_GREEN),
            TextColumn("[bold green]Cancelling timer..."),
            BarColumn(bar_width=40, style=HACKER_GREEN, complete_style=HIGHLIGHT_STYLE),
            expand=True
        ) as progress:
            task = progress.add_task("", total=100)
            for i in range(101):
                progress.update(task, completed=i)
                time.sleep(0.01)
        
        console.print()
        success_msg = Text("Timer cancelled successfully!", style=f"bold {HACKER_GREEN}")
        console.print(Align.center(success_msg))
        time.sleep(1.5)
        clear_screen()
        return True
    else:
        console.print()
        error_msg = Text("No active timer to cancel.", style="yellow")
        console.print(Align.center(error_msg))
        time.sleep(1.5)
        clear_screen()
        return False

def countdown_timer():
    """Background thread to update the countdown timer"""
    global timer_active, end_time
    
    while timer_active:
        time.sleep(1)
        # Check if end_time is None before comparing
        if end_time is not None and time.time() >= end_time:
            timer_active = False
            break
        # Also break if timer has been cancelled (end_time became None)
        if end_time is None:
            break

def display_timer_status():
    """Display the current timer status in a rich table"""
    global timer_active, end_time, timer_type
    
    table = Table(title="[bold green]Active Timer[/bold green]", 
                 show_header=True, header_style="bold green", 
                 box=DOUBLE, border_style=BORDER_STYLE)
    table.add_column("Type", style=MAIN_STYLE)
    table.add_column("Time Remaining", style=MAIN_STYLE)
    table.add_column("End Time", style=MAIN_STYLE)
    
    if timer_active and end_time:
        remaining = end_time - time.time()
        if remaining <= 0:
            timer_active = False
            return Panel("No active timer", border_style=BORDER_STYLE)
            
        hours, remainder = divmod(int(remaining), 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        end_time_str = datetime.datetime.fromtimestamp(end_time).strftime("%H:%M:%S")
        
        table.add_row(timer_type.capitalize(), time_str, end_time_str)
        return Align.center(table)
    else:
        return Panel("No active timer", border_style=BORDER_STYLE)

def show_timer_status_rich():
    """Show the current timer status with rich UI"""
    global timer_active
    
    # Use improved screen clearing
    clear_screen()
    print_banner()
    
    title = Text("Timer Status", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    if timer_active:
        instruction = Text("Press 'c' to cancel the timer or ESC to return", style=f"{HACKER_GREEN}")
        console.print(Align.center(instruction))
        console.print()
        
        try:
            # Create a Live display that won't leave artifacts
            with Live(Align.center(display_timer_status()), 
                      refresh_per_second=4, 
                      console=console,
                      auto_refresh=True,
                      screen=True) as live:  # screen=True ensures proper cleanup
                
                while timer_active and end_time and end_time > time.time():
                    live.update(Align.center(display_timer_status()))
                    time.sleep(0.25)
                    
                    # Check for keypresses
                    if os.name == 'nt' and msvcrt.kbhit():
                        key = msvcrt.getch()
                        if key == b'c' or key == b'C':
                            cancel_shutdown()
                            clear_screen()  # Ensure screen is cleared after cancellation
                            return
                        elif key == b'\x1b':  # ESC
                            clear_screen()  # Ensure screen is cleared before returning
                            return
                    # For Unix systems rely on KeyboardInterrupt
        except KeyboardInterrupt:
            cancel_shutdown()
            clear_screen()
    else:
        message = Panel("No active timer", border_style=BORDER_STYLE)
        console.print(Align.center(message))
        console.print()
        
        instruction = Text("Press any key to return to menu...", style=MAIN_STYLE)
        console.print(Align.center(instruction))
        get_key()  # Wait for any key
        clear_screen()  # Ensure screen is cleared before returning

def view_logs_rich():
    """View shutdown logs in rich UI"""
    logs = read_logs()
    
    clear_screen()
    print_banner()
    
    title = Text("Shutdown Logs", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    if not logs:
        message = Panel("No logs found", border_style=BORDER_STYLE)
        console.print(Align.center(message))
        console.print()
        
        instruction = Text("Press any key to return to menu...", style=MAIN_STYLE)
        console.print(Align.center(instruction))
        get_key()
        clear_screen()
        return
    
    table = Table(box=DOUBLE, border_style=BORDER_STYLE)
    table.add_column("Timestamp", style=MAIN_STYLE)
    table.add_column("Action", style=MAIN_STYLE)
    table.add_column("Duration", style=MAIN_STYLE)
    
    for log in logs:
        parts = log.strip().split(" | ")
        if len(parts) >= 3:
            table.add_row(parts[0], parts[1], parts[2])
    
    console.print(Align.center(table))
    console.print()
    
    instruction = Text("Press any key to return to menu...", style=MAIN_STYLE)
    console.print(Align.center(instruction))
    get_key()
    clear_screen()

def set_timer_rich(action):
    """Set a timer using Rich UI"""
    global timer_active, end_time, timer_type, timer_thread
    
    clear_screen()
    print_banner()
    
    title = Text(f"Setting {action.capitalize()} Timer", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    prompt = Text("Enter time (e.g., 30m, 2h, or 1h 30m 15s):", style=MAIN_STYLE)
    console.print(Align.center(prompt))
    
    help_text = Text("Type 'back' to return or 'exit' to quit.", style=MAIN_STYLE)
    console.print(Align.center(help_text))
    console.print()
    
    # We still use Prompt.ask for text input since it's good for this purpose
    time_input = Prompt.ask("[bold]Time[/bold]")
    
    if time_input.lower() == "exit":
        sys.exit()
    elif time_input.lower() == "back":
        return
    
    # Time parsing logic
    hours_match = re.search(r'(\d+)h', time_input, re.IGNORECASE)
    minutes_match = re.search(r'(\d+)m(?!s)', time_input, re.IGNORECASE)
    seconds_match = re.search(r'(\d+)s', time_input, re.IGNORECASE)
    
    hours = int(hours_match.group(1)) if hours_match else 0
    minutes = int(minutes_match.group(1)) if minutes_match else 0
    seconds = int(seconds_match.group(1)) if seconds_match else 0
    
    total_seconds = hours * 3600 + minutes * 60 + seconds
    
    if total_seconds == 0:
        error_msg = Text("\nInvalid input. Please enter at least one time unit (h, m, s).", style="bold red")
        console.print(Align.center(error_msg))
        time.sleep(2)
        return
    
    console.print()  # Add space before progress bar
    
    # Cancel any existing shutdown
    if timer_active:
        cancel_shutdown()
    
    # Show progress bar while setting up timer
    with Progress(
        SpinnerColumn(spinner_name="dots2", style=HACKER_GREEN),
        TextColumn(f"[bold green]Setting {action} timer..."),
        BarColumn(bar_width=40, style=HACKER_GREEN, complete_style=HIGHLIGHT_STYLE),
        expand=True
    ) as progress:
        task = progress.add_task("", total=100)
        
        # Simulate progress
        for i in range(50):
            progress.update(task, completed=i)
            time.sleep(0.01)
            
        # Actually set the timer
        if action == "shutdown":
            os.system(f"shutdown -s -t {total_seconds}")
        elif action == "restart":
            os.system(f"shutdown -r -t {total_seconds}")
        elif action == "bios":
            os.system(f"shutdown /r /fw /t {total_seconds}")
            
        # Continue progress simulation
        for i in range(50, 101):
            progress.update(task, completed=i)
            time.sleep(0.01)
    
    # Set timer tracking variables
    timer_active = True
    end_time = time.time() + total_seconds
    timer_type = action
    
    # Log the event
    log_event(action, total_seconds)
    
    # Start background timer thread
    timer_thread = threading.Thread(target=countdown_timer)
    timer_thread.daemon = True
    timer_thread.start()
    
    console.print()  # Add space before success message
    
    # Center the success message
    time_str = format_time_display(total_seconds)
    success_msg = Text(f"Your PC will {action} in {time_str.strip()}.", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(success_msg))
    console.print()
    
    return_msg = Text("Press any key to return to menu...", style=MAIN_STYLE)
    console.print(Align.center(return_msg))
    get_key()
    
    # After handling key press, make sure to clear the screen before returning
    clear_screen()
    return

def format_time_display(total_seconds):
    """Format seconds into a human-readable string"""
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_str = ""
    if hours: time_str += f"{hours} hour{'s' if hours > 1 else ''} "
    if minutes: time_str += f"{minutes} minute{'s' if minutes > 1 else ''} "
    if seconds: time_str += f"{seconds} second{'s' if seconds > 1 else ''}"
    return time_str.strip()

def shutdown_settings_menu_rich():
    """Display the shutdown settings submenu with Rich UI"""
    while True:
        if timer_active:
            instruction = Text("Press 'c' to cancel the timer or ESC to return", style=f"{HACKER_GREEN}")
            console.print(Align.center(instruction))
            console.print()
        
        try:
            # Create a Live display that won't leave artifacts
            with Live(Align.center(display_timer_status()), 
                      refresh_per_second=4, 
                      console=console,
                      auto_refresh=True,
                      screen=True) as live:  # screen=True ensures proper cleanup
                
                while timer_active and end_time and end_time > time.time():
                    live.update(Align.center(display_timer_status()))
                    time.sleep(0.25)
                    
                    # Check for keypresses
                    if os.name == 'nt' and msvcrt.kbhit():
                        key = msvcrt.getch()
                        if key == b'c' or key == b'C':
                            cancel_shutdown()
                            clear_screen()  # Ensure screen is cleared after cancellation
                            return
                        elif key == b'\x1b':  # ESC
                            clear_screen()  # Ensure screen is cleared before returning
                            return
                    # For Unix systems rely on KeyboardInterrupt
        except KeyboardInterrupt:
            cancel_shutdown()
            clear_screen()
    else:
        message = Panel("No active timer", border_style=BORDER_STYLE)
        console.print(Align.center(message))
        console.print()
        
        instruction = Text("Press any key to return to menu...", style=MAIN_STYLE)
        console.print(Align.center(instruction))
        get_key()  # Wait for any key
        clear_screen()  # Ensure screen is cleared before returning

def view_logs_rich():
    """View shutdown logs in rich UI"""
    logs = read_logs()
    
    clear_screen()
    print_banner()
    
    title = Text("Shutdown Logs", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    if not logs:
        message = Panel("No logs found", border_style=BORDER_STYLE)
        console.print(Align.center(message))
        console.print()
        
        instruction = Text("Press any key to return to menu...", style=MAIN_STYLE)
        console.print(Align.center(instruction))
        get_key()
        clear_screen()
        return
    
    table = Table(box=DOUBLE, border_style=BORDER_STYLE)
    table.add_column("Timestamp", style=MAIN_STYLE)
    table.add_column("Action", style=MAIN_STYLE)
    table.add_column("Duration", style=MAIN_STYLE)
    
    for log in logs:
        parts = log.strip().split(" | ")
        if len(parts) >= 3:
            table.add_row(parts[0], parts[1], parts[2])
    
    console.print(Align.center(table))
    console.print()
    
    instruction = Text("Press any key to return to menu...", style=MAIN_STYLE)
    console.print(Align.center(instruction))
    get_key()
    clear_screen()

def set_timer_rich(action):
    """Set a timer using Rich UI"""
    global timer_active, end_time, timer_type, timer_thread
    
    clear_screen()
    print_banner()
    
    title = Text(f"Setting {action.capitalize()} Timer", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    prompt = Text("Enter time (e.g., 30m, 2h, or 1h 30m 15s):", style=MAIN_STYLE)
    console.print(Align.center(prompt))
    
    help_text = Text("Type 'back' to return or 'exit' to quit.", style=MAIN_STYLE)
    console.print(Align.center(help_text))
    console.print()
    
    # We still use Prompt.ask for text input since it's good for this purpose
    time_input = Prompt.ask("[bold]Time[/bold]")
    
    if time_input.lower() == "exit":
        sys.exit()
    elif time_input.lower() == "back":
        return
    
    # Time parsing logic
    hours_match = re.search(r'(\d+)h', time_input, re.IGNORECASE)
    minutes_match = re.search(r'(\d+)m(?!s)', time_input, re.IGNORECASE)
    seconds_match = re.search(r'(\d+)s', time_input, re.IGNORECASE)
    
    hours = int(hours_match.group(1)) if hours_match else 0
    minutes = int(minutes_match.group(1)) if minutes_match else 0
    seconds = int(seconds_match.group(1)) if seconds_match else 0
    
    total_seconds = hours * 3600 + minutes * 60 + seconds
    
    if total_seconds == 0:
        error_msg = Text("\nInvalid input. Please enter at least one time unit (h, m, s).", style="bold red")
        console.print(Align.center(error_msg))
        time.sleep(2)
        return
    
    console.print()  # Add space before progress bar
    
    # Cancel any existing shutdown
    if timer_active:
        cancel_shutdown()
    
    # Show progress bar while setting up timer
    with Progress(
        SpinnerColumn(spinner_name="dots2", style=HACKER_GREEN),
        TextColumn(f"[bold green]Setting {action} timer..."),
        BarColumn(bar_width=40, style=HACKER_GREEN, complete_style=HIGHLIGHT_STYLE),
        expand=True
    ) as progress:
        task = progress.add_task("", total=100)
        
        # Simulate progress
        for i in range(50):
            progress.update(task, completed=i)
            time.sleep(0.01)
            
        # Actually set the timer
        if action == "shutdown":
            os.system(f"shutdown -s -t {total_seconds}")
        elif action == "restart":
            os.system(f"shutdown -r -t {total_seconds}")
        elif action == "bios":
            os.system(f"shutdown /r /fw /t {total_seconds}")
            
        # Continue progress simulation
        for i in range(50, 101):
            progress.update(task, completed=i)
            time.sleep(0.01)
    
    # Set timer tracking variables
    timer_active = True
    end_time = time.time() + total_seconds
    timer_type = action
    
    # Log the event
    log_event(action, total_seconds)
    
    # Start background timer thread
    timer_thread = threading.Thread(target=countdown_timer)
    timer_thread.daemon = True
    timer_thread.start()
    
    console.print()  # Add space before success message
    
    # Center the success message
    time_str = format_time_display(total_seconds)
    success_msg = Text(f"Your PC will {action} in {time_str.strip()}.", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(success_msg))
    console.print()
    
    return_msg = Text("Press any key to return to menu...", style=MAIN_STYLE)
    console.print(Align.center(return_msg))
    get_key()
    
    # After handling key press, make sure to clear the screen before returning
    clear_screen()
    return

def format_time_display(total_seconds):
    """Format seconds into a human-readable string"""
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_str = ""
    if hours: time_str += f"{hours} hour{'s' if hours > 1 else ''} "
    if minutes: time_str += f"{minutes} minute{'s' if minutes > 1 else ''} "
    if seconds: time_str += f"{seconds} second{'s' if seconds > 1 else ''}"
    return time_str.strip()

def shutdown_settings_menu_rich():
    """Display the shutdown settings submenu with Rich UI"""
    while True:
        options = [
            "Set Shutdown Timer", 
            "Set Restart Timer",
            "Advanced Shutdown Options",  # Added this option as #2
            "Set Boot to BIOS Timer",
            "Cancel Active Timer", 
            "Back to Features Menu"
        ]
        
        choice = arrow_menu("Shutdown Settings", options)
        
        # Clear screen before processing the choice
        clear_screen()
        
        if choice == 0:
            set_timer_rich("shutdown")
        elif choice == 1:
            set_timer_rich("restart")
        elif choice == 2:
            advanced_shutdown_menu()  # New function call
        elif choice == 3:
            set_timer_rich("bios")
        elif choice == 4:
            cancel_shutdown()
        elif choice == 5 or choice == -1:  # Selected "Back" or pressed ESC
            clear_screen()
            return

def advanced_shutdown_menu():
    """Advanced shutdown options menu"""
    while True:
        options = [
            "Process Completion Shutdown",
            "Schedule Calendar Shutdown",  # New option for next feature
            "Back to Shutdown Settings"
        ]
        
        choice = arrow_menu("Advanced Shutdown Options", options)
        
        # Clear screen before processing the choice
        clear_screen()
        
        if choice == 0:
            process_completion_shutdown()
        elif choice == 1:
            calendar_scheduling_placeholder()
        elif choice == 2 or choice == -1:  # Selected "Back" or pressed ESC
            clear_screen()
            return

def process_completion_shutdown():
    """Set up a shutdown that waits for specified processes to complete"""
    # Create global variable to store monitored processes
    global monitored_processes
    
    # Initialize if not already defined
    if not hasattr(sys.modules[__name__], 'monitored_processes'):
        monitored_processes = []
    
    while True:
        clear_screen()
        print_banner()
        
        title = Text("Process Completion Shutdown", style=f"bold {HACKER_GREEN}")
        console.print(Align.center(title))
        console.print()
        
        options = [
            "Select Process to Monitor", 
            "Enter Process Name Manually",
            "View Selected Processes",
            "Start Monitoring",
            "Clear Selected Processes",
            "Back to Advanced Settings"
        ]
        
        choice = arrow_menu("Process Completion Options", options)
        
        clear_screen()
        
        if choice == 0:
            select_running_process()
        elif choice == 1:
            enter_process_manually()
        elif choice == 2:
            view_selected_processes()
        elif choice == 3:
            start_process_monitoring()
        elif choice == 4:
            clear_selected_processes()
        elif choice == 5 or choice == -1:  # Selected "Back" or pressed ESC
            return

def select_running_process():
    """Select a running process to monitor"""
    global monitored_processes
    
    clear_screen()
    print_banner()
    
    title = Text("Select Running Process", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    message = Text("Loading running processes...", style=MAIN_STYLE)
    console.print(Align.center(message))
    
    # Get running processes
    running_processes = []
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # Get process info
                process_info = proc.info
                running_processes.append((process_info['pid'], process_info['name']))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception as e:
        error_msg = Text(f"Error: {str(e)}", style="bold red")
        console.print(Align.center(error_msg))
        console.print()
        
        instruction = Text("Press any key to return...", style=MAIN_STYLE)
        console.print(Align.center(instruction))
        get_key()
        return
    
    if not running_processes:
        message = Text("No processes found.", style="bold red")
        console.print(Align.center(message))
        console.print()
        
        instruction = Text("Press any key to return...", style=MAIN_STYLE)
        console.print(Align.center(instruction))
        get_key()
        return
    
    # Sort by name for easier browsing
    running_processes.sort(key=lambda x: x[1].lower())
    
    # Create a list of process names with PIDs for the menu
    process_list = [f"{name} (PID: {pid})" for pid, name in running_processes]
    process_list.append("Back")
    
    # Display process selection menu with pagination
    page_size = 15
    current_page = 0
    total_pages = (len(process_list) + page_size - 1) // page_size
    
    while True:
        clear_screen()
        print_banner()
        
        title = Text("Select Process to Monitor", style=f"bold {HACKER_GREEN}")
        console.print(Align.center(title))
        console.print()
        
        # Show pagination info
        pagination = Text(f"Page {current_page + 1} of {total_pages}", style=MAIN_STYLE)
        console.print(Align.center(pagination))
        console.print()
        
        # Get processes for current page
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, len(process_list))
        current_page_processes = process_list[start_idx:end_idx]
        
        # Show process selection menu
        process_choice = arrow_menu("Select a process", current_page_processes)
        
        if process_choice == -1:  # ESC pressed
            return
        
        # Calculate actual index including pagination
        actual_choice = start_idx + process_choice
        
        if actual_choice >= len(running_processes):  # "Back" option selected
            return
        
        # Process was selected - add to monitored list
        selected_pid, selected_name = running_processes[actual_choice]
        
        # Check if already in list
        if any(p.get('pid') == selected_pid for p in monitored_processes):
            clear_screen()
            print_banner()
            console.print(Align.center(Text(f"Process {selected_name} is already being monitored.", style="yellow")))
            time.sleep(1.5)
            continue
        
        # Add to monitored processes
        monitored_processes.append({
            'pid': selected_pid,
            'name': selected_name,
            'monitor_type': None,  # Will be set when starting monitoring
            'start_time': None
        })
        
        clear_screen()
        print_banner()
        success_msg = Text(f"Added {selected_name} (PID: {selected_pid}) to monitoring list.", style=f"bold {HACKER_GREEN}")
        console.print(Align.center(success_msg))
        time.sleep(1.5)
        
        # Show next page if we've reached the end of this page
        if process_choice == len(current_page_processes) - 1 and current_page < total_pages - 1:
            current_page += 1

def enter_process_manually():
    """Enter a process name manually to monitor"""
    global monitored_processes
    
    clear_screen()
    print_banner()
    
    title = Text("Enter Process Name", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    instruction = Text("Enter the process name (e.g., chrome.exe):", style=MAIN_STYLE)
    console.print(Align.center(instruction))
    console.print()
    
    process_name = Prompt.ask("[bold]Process Name[/bold]")
    
    if not process_name:
        return
        
    if process_name.lower() == 'back':
        return
    
    # Check if already in list
    if any(p.get('name', '').lower() == process_name.lower() for p in monitored_processes):
        console.print()
        console.print(Align.center(Text(f"Process {process_name} is already being monitored.", style="yellow")))
        time.sleep(1.5)
        return
    
    # Add to monitored processes
    monitored_processes.append({
        'pid': None,  # Will try to find PID when monitoring
        'name': process_name,
        'monitor_type': None,  # Will be set when starting monitoring
        'start_time': None
    })
    
    console.print()
    success_msg = Text(f"Added {process_name} to monitoring list.", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(success_msg))
    console.print()
    
    instruction = Text("Press any key to continue...", style=MAIN_STYLE)
    console.print(Align.center(instruction))
    get_key()

def view_selected_processes():
    """View the list of processes selected for monitoring"""
    global monitored_processes
    
    clear_screen()
    print_banner()
    
    title = Text("Selected Processes", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    if not monitored_processes:
        message = Text("No processes selected for monitoring.", style="yellow")
        console.print(Align.center(message))
    else:
        # Create a table to display selected processes
        table = Table(box=DOUBLE, border_style=BORDER_STYLE)
        table.add_column("Process Name", style=MAIN_STYLE)
        table.add_column("PID", style=MAIN_STYLE)
        
        for process in monitored_processes:
            pid = str(process.get('pid')) if process.get('pid') is not None else "Auto-detect"
            table.add_row(process.get('name', 'Unknown'), pid)
        
        console.print(Align.center(table))
    
    console.print()
    instruction = Text("Press any key to continue...", style=MAIN_STYLE)
    console.print(Align.center(instruction))
    get_key()

def clear_selected_processes():
    """Clear the list of selected processes"""
    global monitored_processes
    
    clear_screen()
    print_banner()
    
    title = Text("Clear Selected Processes", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    if not monitored_processes:
        message = Text("No processes are currently selected.", style="yellow")
        console.print(Align.center(message))
    else:
        prompt = Text(f"Clear all {len(monitored_processes)} selected processes?", style=MAIN_STYLE)
        console.print(Align.center(prompt))
        console.print()
        
        confirm = Confirm.ask("[bold]Confirm[/bold]")
        
        if confirm:
            monitored_processes = []
            console.print()
            success_msg = Text("All selected processes have been cleared.", style=f"bold {HACKER_GREEN}")
            console.print(Align.center(success_msg))
        else:
            console.print()
            message = Text("Operation cancelled.", style="yellow")
            console.print(Align.center(message))
    
    console.print()
    instruction = Text("Press any key to continue...", style=MAIN_STYLE)
    console.print(Align.center(instruction))
    get_key()

def start_process_monitoring():
    """Start monitoring selected processes and shut down when they complete"""
    global monitored_processes
    
    if not monitored_processes:
        clear_screen()
        print_banner()
        
        message = Text("No processes selected for monitoring.", style="yellow")
        console.print(Align.center(message))
        console.print()
        
        instruction = Text("Press any key to return...", style=MAIN_STYLE)
        console.print(Align.center(instruction))
        get_key()
        return
    
    # Choose monitoring method
    clear_screen()
    print_banner()
    
    title = Text("Select Monitoring Method", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    explanation = [
        "Choose how to determine when processes have completed:",
        "1. Process + Disk Activity: Monitor process existence and disk activity",
        "2. Process + Network Activity: Monitor process existence and network activity"
    ]
    
    for line in explanation:
        console.print(Align.center(Text(line, style=MAIN_STYLE)))
    
    console.print()
    
    options = [
        "Process + Disk Activity",
        "Process + Network Activity",
        "Back"
    ]
    
    method_choice = arrow_menu("Select Monitoring Method", options)
    
    if method_choice == 2 or method_choice == -1:  # "Back" or ESC
        return
    
    # Set the monitoring type for all processes
    monitor_type = "disk" if method_choice == 0 else "network"
    
    # Choose action after processes complete
    clear_screen()
    print_banner()
    
    title = Text("Select Action", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    prompt = Text("What action should be taken when processes complete?", style=MAIN_STYLE)
    console.print(Align.center(prompt))
    console.print()
    
    action_options = [
        "Shutdown Computer",
        "Restart Computer",
        "Back"
    ]
    
    action_choice = arrow_menu("Select Action", action_options)
    
    if action_choice == 2 or action_choice == -1:  # "Back" or ESC
        return
    
    action = "shutdown" if action_choice == 0 else "restart"
    
    # Choose delay time before action
    clear_screen()
    print_banner()
    
    title = Text("Delay Before Action", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    prompt = Text("Enter delay time before action (in seconds):", style=MAIN_STYLE)
    console.print(Align.center(prompt))
    console.print()
    
    delay_input = Prompt.ask("[bold]Delay (seconds)[/bold]", default="60")
    
    try:
        delay = max(10, int(delay_input))  # Minimum 10 seconds
    except ValueError:
        delay = 60  # Default if invalid input
    
    # Update monitor type and start time for each process
    for process in monitored_processes:
        process['monitor_type'] = monitor_type
        process['start_time'] = time.time()
    
    # Start monitoring
    monitor_processes_until_completion(action, delay)

def is_process_running(process_info):
    """Check if a process is still running"""
    # If we have a PID, check if that process is still running
    if process_info.get('pid'):
        try:
            process = psutil.Process(process_info['pid'])
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            pass
    
    # If no PID or PID not found, try to find by name
    process_name = process_info.get('name', '').lower()
    if process_name:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'].lower() == process_name:
                    # Update the PID if we find a match
                    process_info['pid'] = proc.info['pid']
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    
    return False

def is_process_active(process_info):
    """Check if a process is active based on its monitor type"""
    if not is_process_running(process_info):
        return False
    
    try:
        # Get the process object
        if not process_info.get('pid'):
            return False
            
        process = psutil.Process(process_info['pid'])
        monitor_type = process_info.get('monitor_type', 'disk')
        
        if monitor_type == 'disk':
            # Check disk activity
            try:
                io_counters = process.io_counters()
                # Store previous counters if they exist
                prev_counters = process_info.get('prev_io_counters')
                process_info['prev_io_counters'] = io_counters
                
                # If we have previous counters, check for activity
                if prev_counters:
                    read_diff = io_counters.read_bytes - prev_counters.read_bytes
                    write_diff = io_counters.write_bytes - prev_counters.write_bytes
                    
                    # Consider active if there's significant I/O (more than 1KB)
                    return read_diff > 1024 or write_diff > 1024
                
                return True  # First check, assume active
            except (psutil.AccessDenied, AttributeError):
                # If we can't get I/O counters, fall back to just checking if running
                return True
        elif monitor_type == 'network':
            # Check network activity
            try:
                connections = process.connections()
                # Any active connection means the process is active
                return len(connections) > 0
            except (psutil.AccessDenied, AttributeError):
                # If we can't get connections, check if it has any network activity
                try:
                    net_io = process.net_io_counters()
                    prev_net_io = process_info.get('prev_net_io')
                    process_info['prev_net_io'] = net_io
                    
                    if prev_net_io:
                        sent_diff = net_io.bytes_sent - prev_net_io.bytes_sent
                        recv_diff = net_io.bytes_recv - prev_net_io.bytes_recv
                        
                        # Consider active if there's significant network activity
                        return sent_diff > 1024 or recv_diff > 1024
                    
                    return True  # First check, assume active
                except (psutil.AccessDenied, AttributeError):
                    # If we can't get network I/O either, fall back to just checking if running
                    return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    
    return True  # Default to assuming active if all else fails

def monitor_processes_until_completion(action, delay):
    """Monitor processes until they all complete, then perform action"""
    global monitored_processes
    
    if not monitored_processes:
        return
    
    clear_screen()
    print_banner()
    
    title = Text("Process Monitoring Active", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    instruction = Text("Waiting for processes to complete...", style=MAIN_STYLE)
    console.print(Align.center(instruction))
    console.print()
    
    cancel_instruction = Text("Press ESC to cancel monitoring", style=MAIN_STYLE)
    console.print(Align.center(cancel_instruction))
    console.print()
    
    # Table to show status
    table = Table(box=DOUBLE, border_style=BORDER_STYLE)
    table.add_column("Process Name", style=MAIN_STYLE)
    table.add_column("Status", style=MAIN_STYLE)
    
    # Initialize process status
    process_status = {p.get('name', 'Unknown'): "Running" for p in monitored_processes}
    
    # Create a live display for real-time updates
    with Live(auto_refresh=True, refresh_per_second=1, console=console) as live:
        inactivity_threshold = 30  # seconds
        completed_processes = set()
        
        while True:
            # Check for keypress to cancel
            if os.name == 'nt' and msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b'\x1b':  # ESC key
                    console.print()
                    console.print(Align.center(Text("Monitoring cancelled.", style="yellow")))
                    time.sleep(1.5)
                    return
            
            # Update table with current process status
            table = Table(box=DOUBLE, border_style=BORDER_STYLE, title=f"[{HACKER_GREEN}]Monitoring Processes[/{HACKER_GREEN}]")
            table.add_column("Process Name", style=MAIN_STYLE)
            table.add_column("Status", style=MAIN_STYLE)
            
            all_completed = True
            
            for process in monitored_processes:
                name = process.get('name', 'Unknown')
                
                if name in completed_processes:
                    status_text = Text("Completed", style=f"bold {HACKER_GREEN}")
                    table.add_row(name, status_text)
                    continue
                
                # Check if process is running
                if not is_process_running(process):
                    status_text = Text("Not Running", style="bold yellow")
                    table.add_row(name, status_text)
                    completed_processes.add(name)
                    continue
                
                # Process is running, check if active
                if is_process_active(process):
                    # Reset inactivity time if active
                    process['last_active'] = time.time()
                    status_text = Text("Active", style=MAIN_STYLE)
                    table.add_row(name, status_text)
                    all_completed = False
                else:
                    # Check how long it's been inactive
                    last_active = process.get('last_active', time.time())
                    inactive_time = time.time() - last_active
                    
                    if inactive_time >= inactivity_threshold:
                        status_text = Text("Inactive (Complete)", style=f"bold {HACKER_GREEN}")
                        table.add_row(name, status_text)
                        completed_processes.add(name)
                    else:
                        remaining = inactivity_threshold - inactive_time
                        status_text = Text(f"Inactive ({remaining:.0f}s)", style="yellow")
                        table.add_row(name, status_text)
                        all_completed = False
            
            # Update the live display
            live_display = []
            live_display.append(Align.center(table))
            
            if all_completed and monitored_processes:
                live_display.append(Text("\n"))
                live_display.append(Align.center(Text("All processes have completed!", style=f"bold {HACKER_GREEN}")))
                live_display.append(Text("\n"))
                live_display.append(Align.center(Text(f"{action.capitalize()} will begin in {delay} seconds...", style=f"bold {HACKER_GREEN}")))
                
                # Update display
                live.update(Columns(live_display))
                time.sleep(2)
                
                # Execute the action after delay
                execute_delayed_action(action, delay)
                return
            
            # Not all processes are complete, continue monitoring
            live.update(Columns(live_display))
            time.sleep(1)

def execute_delayed_action(action, delay):
    """Execute the specified action after a delay"""
    clear_screen()
    print_banner()
    
    title = Text(f"Preparing to {action.capitalize()}", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    message = Text(f"All monitored processes have completed.", style=MAIN_STYLE)
    console.print(Align.center(message))
    console.print()
    
    cancel_msg = Text("Press ESC to cancel", style=MAIN_STYLE)
    console.print(Align.center(cancel_msg))
    console.print()
    
    # Create countdown progress bar
    with Progress(
        TextColumn("[bold green]Time remaining: "),
        BarColumn(bar_width=40, style=HACKER_GREEN, complete_style=HIGHLIGHT_STYLE),
        TextColumn("[bold green]{task.fields[time_remaining]}"),
        expand=True,
        console=console
    ) as progress:
        task = progress.add_task("", total=delay, time_remaining=format_seconds(delay))
        
        for remaining in range(delay, 0, -1):
            if os.name == 'nt' and msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b'\x1b':  # ESC key
                    progress.stop()
                    console.print()
                    console.print(Align.center(Text(f"{action.capitalize()} cancelled.", style="yellow")))
                    time.sleep(1.5)
                    return
            
            progress.update(task, completed=delay - remaining + 1, time_remaining=format_seconds(remaining - 1))
            time.sleep(1)
    
    # Execute the action
    console.print()
    console.print(Align.center(Text(f"Executing {action}...", style=f"bold {HACKER_GREEN}")))
    
    if action == "shutdown":
        os.system("shutdown /s /t 0")
    else:  # restart
        os.system("shutdown /r /t 0")
    
    time.sleep(5)  # Just in case the shutdown command takes a moment

def format_seconds(seconds):
    """Format seconds into mm:ss format"""
    minutes, secs = divmod(seconds, 60)
    return f"{minutes:02d}:{secs:02d}"

def calendar_scheduling_placeholder():
    """Placeholder for calendar scheduling feature"""
    clear_screen()
    print_banner()
    
    title = Text("Calendar Scheduling", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    message = Text("Coming soon: Schedule shutdowns for specific dates/times", style=MAIN_STYLE)
    console.print(Align.center(message))
    console.print()
    
    instruction = Text("Press any key to return to menu...", style=MAIN_STYLE)
    console.print(Align.center(instruction))
    get_key()
    clear_screen()

def features_menu_rich():
    """Display the features menu with Rich UI"""
    while True:
        options = [
            "Shutdown Settings", 
            "Network Tools",
            "View Timer Status", 
            "View Logs", 
            "Back to Main Menu"
        ]
        
        choice = arrow_menu("Main Features", options)
        
        # Clear screen before processing the choice
        clear_screen()
        
        if choice == 0:
            shutdown_settings_menu_rich()
        elif choice == 1:
            network_tools_menu_rich()
        elif choice == 2:
            show_timer_status_rich()
        elif choice == 3:
            view_logs_rich()
        elif choice == 4 or choice == -1:  # Selected "Back" or pressed ESC
            clear_screen()
            return

def network_tools_menu_rich():
    """Display the network tools submenu with Rich UI"""
    while True:
        options = [
            "What's My IP Address", 
            "IP Address Information",
            "Back to Features Menu"
        ]
        
        choice = arrow_menu("Network Tools", options)
        
        # Clear screen before processing the choice
        clear_screen()
        
        if choice == 0:
            show_my_ip()
        elif choice == 1:
            lookup_ip_info()
        elif choice == 2 or choice == -1:  # Selected "Back" or pressed ESC
            clear_screen()
            return

def show_my_ip():
    """Display the local IP address and computer name"""
    clear_screen()
    print_banner()
    
    title = Text("My IP Address", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    # Create spinner while gathering info
    with Progress(
        SpinnerColumn(spinner_name="dots2", style=HACKER_GREEN),
        TextColumn("[bold green]Getting IP address information..."),
        expand=True
    ) as progress:
        progress.add_task("", total=None)
        
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            
            # Try to get external IP
            external_ip = "Unknown"
            try:
                with urllib.request.urlopen("https://api.ipify.org") as response:
                    external_ip = response.read().decode('utf-8')
            except:
                pass
        except Exception as e:
            error_msg = f"Error retrieving IP address: {str(e)}"
            console.print(Align.center(Text(error_msg, style="bold red")))
            console.print()
    
    # Create table for displaying IP information
    table = Table(box=DOUBLE, border_style=BORDER_STYLE)
    table.add_column("Information", style=MAIN_STYLE)
    table.add_column("Value", style=MAIN_STYLE)
    
    table.add_row("Computer Name", hostname)
    table.add_row("Local IP Address", local_ip)
    table.add_row("External IP Address", external_ip)
    
    console.print(Align.center(table))
    console.print()
    
    instruction = Text("Press any key to return to menu...", style=MAIN_STYLE)
    console.print(Align.center(instruction))
    get_key()
    clear_screen()

def lookup_ip_info():
    """Look up information about an IP address"""
    clear_screen()
    print_banner()
    
    title = Text("IP Address Information", style=f"bold {HACKER_GREEN}")
    console.print(Align.center(title))
    console.print()
    
    prompt = Text("Enter an IP address to lookup:", style=MAIN_STYLE)
    console.print(Align.center(prompt))
    
    help_text = Text("Type 'back' to return or 'exit' to quit.", style=MAIN_STYLE)
    console.print(Align.center(help_text))
    console.print()
    
    ip_input = Prompt.ask("[bold]IP Address[/bold]")
    
    if ip_input.lower() == "exit":
        sys.exit()
    elif ip_input.lower() == "back":
        return
    
    console.print()
    
    # Create spinner while gathering info
    with Progress(
        SpinnerColumn(spinner_name="dots2", style=HACKER_GREEN),
        TextColumn(f"[bold green]Looking up information for {ip_input}..."),
        expand=True
    ) as progress:
        progress.add_task("", total=None)
        
        try:
            # API URL to get IP details
            url = f"http://ip-api.com/json/{ip_input}"
            response = urllib.request.urlopen(url)
            data = json.load(response)
            
            if data.get("status") == "success":
                # Create detailed table with IP information
                table = Table(title=f"[bold green]Information for {data['query']}[/bold green]", 
                             box=DOUBLE, border_style=BORDER_STYLE)
                table.add_column("Property", style=MAIN_STYLE)
                table.add_column("Value", style=MAIN_STYLE)
                
                table.add_row("IP Address", data['query'])
                if 'org' in data:
                    table.add_row("Organization", data['org'])
                if 'isp' in data:
                    table.add_row("ISP", data['isp'])
                if 'city' in data:
                    table.add_row("City", data['city'])
                if 'regionName' in data:
                    table.add_row("Region", data['regionName'])
                if 'country' in data:
                    table.add_row("Country", data['country'])
                if 'lat' in data and 'lon' in data:
                    table.add_row("Latitude", str(data['lat']))
                    table.add_row("Longitude", str(data['lon']))
                    maps_url = f"https://www.google.com/maps/place/{data['lat']}+{data['lon']}"
                    table.add_row("Google Maps", maps_url)
                
                console.print()
                console.print(Align.center(table))
            else:
                error_msg = Text(f"Could not retrieve information for {ip_input}.", style="bold red")
                console.print(Align.center(error_msg))
        except Exception as e:
            error_msg = Text(f"Error looking up IP information: {str(e)}", style="bold red")
            console.print(Align.center(error_msg))
    
    console.print()
    instruction = Text("Press any key to return to menu...", style=MAIN_STYLE)
    console.print(Align.center(instruction))
    get_key()
    clear_screen()

def main_menu_rich():
    """Display the main menu with Rich UI"""
    while True:
        options = ["Main Features", "Exit"]
        choice = arrow_menu("Main Menu", options)
        
        # Clear screen before processing the choice
        clear_screen()
        
        if choice == 0:
            features_menu_rich()
            # No need for another clear_screen here as features_menu_rich already clears
        elif choice == 1 or choice == -1:  # Selected "Exit" or pressed ESC
            clear_screen()
            console.print(Align.center(Text("\nGoodbye!", style=f"bold {HACKER_GREEN}")))
            time.sleep(1)
            sys.exit()

def main():
    # Use Rich UI by default
    try:
        # Check if running in terminal that supports Rich
        if os.environ.get('TERM') != 'dumb' and sys.stdout.isatty():
            signal.signal(signal.SIGINT, lambda x, y: sys.exit(0))
            main_menu_rich()
        else:
            # Fall back to curses if in a limited environment
            curses.wrapper(main)
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        console.print("[yellow]Falling back to curses interface...[/yellow]")
        time.sleep(2)
        curses.wrapper(main)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold green]Goodbye![/bold green]")
        sys.exit(0)