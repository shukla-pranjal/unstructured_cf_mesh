import bpy
import os
import threading
from ..properties import global_state
from .. import utils_system

def run_command_async(command, working_dir, report_callback=None, log_filename="meshing.log"):
    def task():
        global_state.is_running = True
        global_state.is_error = False
        global_state.status_message = "Starting..."

        import subprocess
        all_lines = []
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                executable='/bin/bash',
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,   # merge stderr into stdout for live tail
                text=True,
                bufsize=1                   # line-buffered
            )
            for line in proc.stdout:
                stripped = line.strip()
                if stripped:
                    all_lines.append(stripped)
                    # Show last meaningful line in the status box live
                    global_state.status_message = stripped[:70]

            proc.wait()
            success = (proc.returncode == 0)
            output = "\n".join(all_lines)
        except Exception as e:
            success = False
            output = str(e)

        global_state.last_output = output

        # --- Write full log to file in the case directory ---
        try:
            log_path = os.path.join(working_dir, log_filename)
            with open(log_path, "w") as lf:
                lf.write(output)
            print(f"[cfMesh] Full log written to: {log_path}")
        except Exception as log_err:
            print(f"[cfMesh] Warning: could not write log file: {log_err}")
        if success:
            global_state.status_message = "Finished Successfully"
        else:
            global_state.is_error = True
            # Try to surface a useful FATAL line
            fatal = [l for l in all_lines if "Fatal" in l or "FATAL" in l or "Error" in l]
            err_msg = fatal[-1] if fatal else (all_lines[-1] if all_lines else "Process crashed silently.")
            global_state.status_message = err_msg[:70]

        if report_callback:
            def wrap_callback():
                report_callback(success, output)
                return None
            bpy.app.timers.register(wrap_callback)

        global_state.is_running = False

    global_state.thread = threading.Thread(target=task)
    global_state.thread.start()
    
    bpy.app.timers.register(check_async_status)

def check_async_status():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
            
    if global_state.is_running:
        return 0.5
    return None

def set_ui_error(message):
    """Set an error message that appears in the red alert box in the UI panel."""
    global_state.is_error = True
    global_state.status_message = message

def clear_ui_status():
    """Reset the UI status to idle."""
    global_state.is_error = False
    global_state.status_message = "Idle"
