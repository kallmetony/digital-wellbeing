import psutil

def kill_process(proc_name):
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == proc_name.lower():
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

def is_running(proc_name):
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == proc_name.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False
