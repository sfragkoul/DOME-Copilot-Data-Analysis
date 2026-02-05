import pandas as pd
import json
import numpy as np
import os
import sys

"""
DOME Converter Utility

This script provides bidirectional conversion between TSV and JSON formats for the DOME Registry data.
It relies on local reference schema files to ensure consistent structure and column ordering.

Usage:
    python Convert_Registry_TSV_to_JSON.py <INPUT_FILE>

Arguments:
    <INPUT_FILE>: Path to a .tsv or .json file to convert.

Files Required in same directory:
    - DOME_Registry_Schema_Reference.json (Structure Reference)
    - DOME_Registry_Schema_Reference.tsv  (Header Reference)
"""

# --- Helper Functions ---

def flatten_json_structure(data, parent_key='', sep='/'):
    """
    Flattens a nested JSON dictionary into a version with component path keys.
    e.g. {'dataset': {'availability': 'yes'}} -> {'dataset/availability': 'yes'}
    Preserves $oid and $date via special handling if needed.
    """
    items = []
    for k, v in data.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            # Special case for Mongo types like $oid and $date which we treat as leaf nodes
            if '$oid' in v:
                items.append((f"{new_key}{sep}$oid", v['$oid']))
            elif '$date' in v:
                items.append((f"{new_key}{sep}$date", v['$date']))
            else:
                items.extend(flatten_json_structure(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def set_nested_value(d, keys, value):
    """
    Sets a value in a nested dictionary `d` at path `keys`.
    e.g. keys=['dataset', 'availability']
    """
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value

# --- Conversion Logic ---

def convert_tsv_to_json(input_tsv_path, reference_json_path):
    print(f"\n[Mode: TSV -> JSON]")
    print(f"Input: {input_tsv_path}")
    print(f"Schema Ref: {reference_json_path}")
    
    output_json_path = os.path.splitext(input_tsv_path)[0] + '.json'
    
    try:
        df = pd.read_csv(input_tsv_path, sep='\t')
        print(f"Loaded TSV with {len(df)} records.")
    except Exception as e:
        print(f"Error loading TSV: {e}")
        return

    # Load Reference Schema for structure
    try:
        with open(reference_json_path, 'r') as f:
            reference_data = json.load(f)
            reference_record = reference_data[0] if isinstance(reference_data, list) else reference_data
    except Exception as e:
        print(f"Error loading reference JSON: {e}")
        return

    # Determine schema keys from reference
    flat_ref = flatten_json_structure(reference_record)
    ref_keys_list = list(flat_ref.keys())
    
    # Ensure publication/pmcid is present
    if 'publication/pmcid' not in ref_keys_list:
        if 'publication/pmid' in ref_keys_list:
            idx = ref_keys_list.index('publication/pmid')
            ref_keys_list.insert(idx + 1, 'publication/pmcid')
        else:
            ref_keys_list.append('publication/pmcid')

    converted_records = []
    
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        new_record = {}
        
        for flat_key in ref_keys_list:
            val = row_dict.get(flat_key)
            
            # Handle types and defaults
            if pd.isna(val) or val == "":
                # Defaults based on key names
                if any(x in flat_key for x in ['done', 'skip', 'score', '__v', 'update', 'year', 'pmid']):
                    val = 0
                elif 'public' in flat_key:
                    val = True 
                else:
                    val = ""
            
            # Force integers
            if any(x in flat_key for x in ['done', 'skip', 'score', '__v', 'update', 'year', 'pmid']):
                try:
                    val = int(float(val))
                except:
                    val = 0
            
            path = flat_key.split('/')
            set_nested_value(new_record, path, val)
            
        converted_records.append(new_record)

    try:
        with open(output_json_path, 'w') as f:
            json.dump(converted_records, f, indent=2)
        print(f"SUCCESS: Saved {len(converted_records)} records to {output_json_path}")
    except Exception as e:
        print(f"Error saving JSON: {e}")


def convert_json_to_tsv(input_json_path, reference_tsv_path):
    print(f"\n[Mode: JSON -> TSV]")
    print(f"Input: {input_json_path}")
    print(f"Schema Ref: {reference_tsv_path}")
    
    output_tsv_path = os.path.splitext(input_json_path)[0] + '.tsv'
    
    # Load Input JSON
    try:
        with open(input_json_path, 'r') as f:
            data = json.load(f)
        if not isinstance(data, list):
            data = [data] # Handle single record
        print(f"Loaded JSON with {len(data)} records.")
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return

    # Load Reference Headers
    try:
        with open(reference_tsv_path, 'r') as f:
            header_line = f.readline().strip()
            columns = header_line.split('\t')
    except Exception as e:
        print(f"Error loading reference TSV headers: {e}")
        return

    flattened_rows = []
    for record in data:
        flat_record = flatten_json_structure(record)
        
        # Build row based on columns
        row = {}
        for col in columns:
            val = flat_record.get(col, "")
            row[col] = val
            
        flattened_rows.append(row)
        
    df = pd.DataFrame(flattened_rows, columns=columns)
    
    try:
        df.to_csv(output_tsv_path, sep='\t', index=False)
        print(f"SUCCESS: Saved {len(df)} records to {output_tsv_path}")
    except Exception as e:
        print(f"Error saving TSV: {e}")


def main():
    # Detect default files in current directory
    workspace = os.path.dirname(os.path.abspath(__file__))
    ref_json = os.path.join(workspace, 'DOME_Registry_Schema_Reference.json')
    ref_tsv = os.path.join(workspace, 'DOME_Registry_Schema_Reference.tsv')
    
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        # Default fallback for testing
        input_file = os.path.join(workspace, 'DOME_Registry_Human_Reviews_258_20260205.tsv')
        if not os.path.exists(input_file):
            print("Usage: python Convert_Registry_TSV_to_JSON.py <INPUT_FILE>")
            return

    if not os.path.exists(input_file):
        print(f"Error: Input file not found: {input_file}")
        return

    ext = os.path.splitext(input_file)[1].lower()
    
    if ext == '.tsv':
        if os.path.exists(ref_json):
            convert_tsv_to_json(input_file, ref_json)
        else:
            print(f"Error: Reference JSON schema not found at {ref_json}")
            
    elif ext == '.json':
        if os.path.exists(ref_tsv):
            convert_json_to_tsv(input_file, ref_tsv)
        else:
            print(f"Error: Reference TSV header not found at {ref_tsv}")
            
    else:
        print(f"Error: Unsupported file extension '{ext}'. input must be .tsv or .json")

if __name__ == "__main__":
    main()
