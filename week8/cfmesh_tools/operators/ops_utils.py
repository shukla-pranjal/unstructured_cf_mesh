import bpy
import threading
from ..properties import global_state
from .. import utils_system

def run_command_async(command, working_dir, report_callback=None):
    def task():
        global_state.is_running = True
        global_state.is_error = False
        global_state.status_message = "Processing..."
        global_state.live_log = []
        global_state.progress_percent = 0.0
        global_state.live_log_tail = ""
        
        def live_cb(line):
            global_state.live_log.append(line)
            if len(global_state.live_log) > 50:
                global_state.live_log.pop(0)
            
            clean_line = line.strip()
            if clean_line:
                global_state.live_log_tail = clean_line
            
            # Simple heuristic for cartesianMesh progress
            if "Surface generation" in line or "Reading mesh" in line:
                global_state.progress_percent = 10.0
                global_state.status_message = "Surface generation..."
            elif "Creating octree" in line:
                global_state.progress_percent = 20.0
                global_state.status_message = "Creating octree..."
            elif "Refining octree" in line:
                global_state.progress_percent = 30.0
                global_state.status_message = "Refining octree..."
            elif "Meshing octree" in line or "Creating cells" in line:
                global_state.progress_percent = 50.0
                global_state.status_message = "Creating cells..."
            elif "Creating layers" in line or "Layer generation" in line:
                global_state.progress_percent = 70.0
                global_state.status_message = "Generating boundary layers..."
            elif "Smoothing mesh" in line or "optimisation" in line.lower():
                global_state.progress_percent = 90.0
                global_state.status_message = "Optimizing mesh..."
            elif "foamToSurface" in line:
                global_state.progress_percent = 95.0
                global_state.status_message = "Extracting visualization surface..."
                
        success, output = utils_system.run_cfmesh_command_live(command, working_dir, live_cb)
        
        global_state.progress_percent = 100.0
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
    props = bpy.context.scene.cfmesh_props
    if hasattr(global_state, 'progress_percent'):
        props.progress_percent = global_state.progress_percent
    if hasattr(global_state, 'live_log_tail'):
        props.live_log_tail = global_state.live_log_tail

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
