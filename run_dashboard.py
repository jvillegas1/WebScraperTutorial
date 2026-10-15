"""
Launcher para el Dashboard de Inmuebles.
Ejecuta desde la raíz del proyecto para evitar problemas de imports.
"""

import subprocess
import sys
import os

def main():
    # Asegurarse de estar en el directorio correcto
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    
    # Agregar el directorio al PYTHONPATH
    env = os.environ.copy()
    env['PYTHONPATH'] = project_root
    
    # Ejecutar streamlit
    dashboard_path = os.path.join(project_root, 'scraper', 'dashboard.py')
    
    cmd = [
        sys.executable, '-m', 'streamlit', 'run',
        dashboard_path,
        '--server.headless', 'true',
        '--browser.gatherUsageStats', 'false'
    ]
    
    print("Iniciando Dashboard de Inmuebles...")
    print(f"Directorio: {project_root}")
    print(f"URL: http://localhost:8501")
    print("-" * 50)
    
    subprocess.run(cmd, env=env)

if __name__ == '__main__':
    main()

