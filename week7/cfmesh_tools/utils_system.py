import subprocess
import os

def run_cfmesh_command(command, working_dir=None):
    """
    A basic Python script to execute terminal commands via subprocess.
    Forces /bin/bash as the shell so that 'source' works correctly.
    """
    print(f"Executing: {command}")
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            executable='/bin/bash',
            cwd=working_dir,
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        if result.returncode == 0:
            print("Command executed successfully!")
            print("STDOUT:\n", result.stdout)
            return True, result.stdout
        else:
            print("Command failed!")
            print("STDOUT:\n", result.stdout)
            print("STDERR:\n", result.stderr)
            combined_output = result.stdout + "\n" + result.stderr
            return False, combined_output
            
    except Exception as e:
        print(f"An exception occurred: {e}")
        return False, str(e)

def launch_paraview(base_dir):
    """
    Creates a .foam stub and launches ParaView as a background process.
    """
    foam_file = os.path.join(base_dir, "case.foam")
    if not os.path.exists(foam_file):
        with open(foam_file, "w") as f:
            pass
    
    print(f"Launching ParaView for: {foam_file}")
    try:
        subprocess.Popen(["paraview", foam_file])
        return True
    except Exception as e:
        print(f"Failed to launch ParaView: {e}")
        return False

def open_directory(path):
    """
    Opens the path in the OS default file explorer.
    """
    if os.path.isdir(path):
        subprocess.Popen(["xdg-open", path])
        return True
    return False
