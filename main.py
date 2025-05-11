import subprocess

# List of script filenames to run in order
scripts = ['deleteoutofstock.py', 'urltext.py', 'scrape.py']

for script in scripts:
    print(f"Running {script}...")
    result = subprocess.run(['python', script])
    if result.returncode != 0:
        print(f"{script} failed with return code {result.returncode}")
        break
    print(f"{script} completed successfully.\n")
