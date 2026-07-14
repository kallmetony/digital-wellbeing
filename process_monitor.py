import psutil

def kill_process(proc_names):
    if isinstance(proc_names, str):
        proc_names = [proc_names]
    target_names = {name.lower() for name in proc_names}
    
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() in target_names:
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

def is_running(proc_names):
    if isinstance(proc_names, str):
        proc_names = [proc_names]
    target_names = {name.lower() for name in proc_names}
    
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() in target_names:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False
