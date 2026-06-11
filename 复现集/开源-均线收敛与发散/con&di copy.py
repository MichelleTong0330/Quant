import h5py

DATA_DIR = '/Users/tongxin/Desktop/念空/复现集/均线收敛与发散/均线收敛数据/data'

def inspect(fpath, max_items=5):
    print(f'\n{"="*60}\n{fpath}')
    def _walk(name, obj):
        t = 'GROUP' if isinstance(obj, h5py.Group) else 'DATASET'
        shape = obj.shape if hasattr(obj, 'shape') else '-'
        dtype = obj.dtype if hasattr(obj, 'dtype') else '-'
        print(f'  {t}  {name}  shape={shape}  dtype={dtype}')
        if isinstance(obj, h5py.Dataset) and obj.size > 0:
            try:
                sample = obj[()] if obj.size <= 5 else obj[0:3]
                print(f'    sample: {sample}')
            except:
                pass
    with h5py.File(fpath, 'r') as f:
        f.visititems(_walk)

import os
for fname in ['adjclose.h5', 'volume.h5', 'amount.h5', 'turn.h5', 'calendar.h5']:
    inspect(os.path.join(DATA_DIR, fname))

# meta_Dataset 单独看
import pickle
meta_path = os.path.join(DATA_DIR, 'meta_Dataset')
with open(meta_path, 'rb') as f:
    obj = pickle.load(f)
print(f'\nmeta_Dataset type={type(obj)}')
if hasattr(obj, 'columns'):
    print(f'  columns={list(obj.columns)}')
    print(obj.head(3))
elif isinstance(obj, dict):
    print(f'  keys={list(obj.keys())[:10]}')