import subprocess
import sys
import os

def run_step(command, description):
    print("\n--------------------------------------------------")
    print(f"RUNNING: {description}")
    print(f"Command: {command}")
    print("--------------------------------------------------")
    
    # Run command and print real-time output
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    # Determine local system encoding for printing safely
    out_enc = sys.stdout.encoding or 'cp949'
    
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            stripped = output.strip()
            # Safely encode/decode to replace illegal characters for console display
            safe_str = stripped.encode(out_enc, errors='replace').decode(out_enc)
            print("  " + safe_str)
            
    rc = process.poll()
    if rc != 0:
        print(f"\n[ERROR] '{description}' failed with exit code {rc}!")
        return False
    print(f"[SUCCESS] '{description}' completed successfully.")
    return True

def main():
    print("==================================================")
    print(" STARTING SUWON REAL ESTATE INTEGRATION PIPELINE")
    print("==================================================")
    
    # Step 1: Run build_real_estate.py to fetch latest data & news
    if not run_step("python build_real_estate.py", "Data Scraping and Pre-analysis Update"):
        print("\n[ERROR] Pipeline aborted due to Step 1 failure.")
        sys.exit(1)
        
    # Step 2: Run ml_pipeline.py to run Scikit-Learn & PyTorch ML/DL models
    if not run_step("python ml_pipeline.py", "ML and Deep Learning Model Training/Prediction"):
        print("\n[ERROR] Pipeline aborted due to Step 2 failure.")
        sys.exit(1)
        
    # Step 3: Run test_harness.py to run validation checks
    if not run_step("python test_harness.py", "Test and Validation Quality Harness"):
        print("\n[ERROR] Pipeline aborted due to Step 3 failure. Quality checks failed!")
        sys.exit(1)
        
    # Step 4: Synchronize HTML files to ensure both URLs are consistent
    print("\n--------------------------------------------------")
    print("SYNCHRONIZING: index.html -> suwon_real_estate.html")
    print("--------------------------------------------------")
    try:
        import shutil
        shutil.copyfile("index.html", "suwon_real_estate.html")
        print("[SUCCESS] HTML files synchronized.")
    except Exception as e:
        print(f"[ERROR] HTML synchronization failed: {e}!")
        sys.exit(1)
        
    print("\n==================================================")
    print(" PIPELINE RUN COMPLETED SUCCESSFULLY!")
    print(" All data scraped, ML models trained, and checks passed.")
    print("==================================================")
    sys.exit(0)

if __name__ == '__main__':
    main()
