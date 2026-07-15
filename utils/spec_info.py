import re
import os.path as osp

spec_bmks = {
        '06': {
            'int': [
                'perlbench',
                'bzip2',
                'gcc',
                'mcf',
                'gobmk',
                'hmmer',
                'sjeng',
                'libquantum',
                'h264ref',
                'omnetpp',
                'astar',
                'xalancbmk',
                ],
            'float':[
                'bwaves', 'gamess', 'milc', 'zeusmp', 'gromacs',
                'cactusADM', 'leslie3d', 'namd', 'dealII', 'soplex',
                'povray', 'calculix', 'GemsFDTD', 'tonto', 'lbm',
                'wrf', 'sphinx3',
                ],
            'high_squash': ['astar', 'bzip2', 'gobmk', 'sjeng'],
            },
        '17': {
            'int': ['perlbench', 'gcc', 'mcf', 'omnetpp', 'xalancbmk', 'x264', 'deepsjeng', 'leela', 'exchange2', 'xz'],
            'float': ['bwaves', 'cactuBSSN', 'namd', 'parest', 'povray', 'lbm', 'wrf', 'blender', 'cam4', 'imagick', 'nab', 'fotonik3d', 'roms'],
            },
        '26': {
            'int': [
                '706.stockfish',
                '707.ntest',
                '708.sqlite',
                '710.omnetpp',
                '714.cpython',
                '721.gcc',
                '723.llvm',
                '727.cppcheck',
                '729.abc',
                '734.vpr',
                '735.gem5',
                '750.sealcrypto',
                '753.ns3',
                '777.zstd',
                ],
            'float': [
                '709.cactus',
                '722.palm',
                '731.astcenc',
                '736.ocio',
                '737.gmsh',
                '748.flightdm',
                '749.fotonik3d',
                '765.roms',
                '766.femflow',
                '767.nest',
                '772.marian',
                '782.lbm',
                ],
            },
        }

def get_insts(fname: str):
    print(fname)
    assert osp.isfile(fname)
    p = re.compile('total guest instructions = (\d+(?:,\d+)*)')
    with open(fname) as f:
        for line in f:
            m = p.search(line)
            if m is not None:
                return m.group(1)
    return None
