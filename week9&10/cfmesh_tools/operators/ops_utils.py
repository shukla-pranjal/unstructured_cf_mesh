import bpy
import threading
from ..properties import global_state
from .. import utils_system

def run_command_async(command, working_dir, report_callback=None):
    def task():
        global_state.is_running = True
        global_state.is_error = False
        global_state.status_message = "Processing..."
        
        success, output = utils_system.run_cfmesh_command(command, working_dir)
        
        global_state.last_output = output
        if success:
            global_state.status_message = "Finished Successfully"
        else:
            global_state.is_error = True
            lines = [line.strip() for line in output.split('\n') if line.strip()]
            if lines:
                err_msg = lines[-1]
                if "FatalError" in output or "FATAL" in output:
                    for line in lines:
                        if "Fatal" in line or "FATAL" in line:
                            err_msg = line
                            break
                global_state.status_message = f"{err_msg[:60]}..." if len(err_msg) > 60 else err_msg
            else:
                global_state.status_message = "Error: Process crashed silently."
        
        if report_callback:
            # Schedule the callback to run in the main thread
            def wrap_callback():
                report_callback(success, output)
                return None
            import bpy
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
