import argparse
import re  
import os  
import csv  

def extract_info_from_log(file_path):
    #print(f"get file: {file_path}")

    instrCnt, cycleCnt, IPC = None, None, None  

    with open(file_path, 'r') as file:
        content = file.read()
    pattern = r'instrCnt = (\d+), cycleCnt = (\d+), IPC = ([\d.]+)'
    match = re.search(pattern, content)
    if match:
        instrCnt = int(match.group(1))
        cycleCnt = int(match.group(2))
        IPC = float(match.group(3))
        #print(f"debug: instrCnt={instrCnt}, cycleCnt={cycleCnt}, IPC={IPC}")
    else:
        print("not find performance data to " + str(file_path))

    pattern = r'.*/checkpoint-0-0-0/([^/]+)/(\d+)/_\d+_([0-9.]+)_\.zstd'
    match = re.search(pattern, content)
    
    if match:
        benchmark = match.group(1)
        checkpoint = match.group(2)
        weights = float(match.group(3))

    #print(f'{benchmark} {checkpoint} {instrCnt} {cycleCnt} {IPC} {weights}')
    return benchmark, checkpoint, instrCnt, cycleCnt, IPC , weights
  
def main():
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--logfile', type=str, required=True, help='log list path')
    parser.add_argument('--outfile', type=str, required=True, help='out csv path')
    args = parser.parse_args()
    log_dir = args.logfile
    output_csv = args.outfile

    header = ['', 'workload', 'bmk', 'point', 'instrCnt', 'Cycles', 'ipc', 'weight']  
    with open(output_csv, 'w', newline='') as csvfile:  
        writer = csv.writer(csvfile)  
        writer.writerow(header)  
        for filename in os.listdir(log_dir):
            if filename.endswith('.log'):
                file_path = os.path.join(log_dir, filename)
                workload, point, instrCnt, cycleCnt, IPC, weights = extract_info_from_log(file_path)
                if all([workload, point, instrCnt, cycleCnt, IPC, weights]):
                    program_name = f"{workload}_{point}"
                    bmk = workload.split('_')[0]
                    writer.writerow([program_name, workload, bmk, point, instrCnt, cycleCnt, IPC, weights])

if __name__ == '__main__':
    main()