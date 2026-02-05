import re
import requests
import json
import sys
import time
import os
import xml.etree.ElementTree as ET

def clean_and_extract_doi(input_string):
    """
    Extracts and standardizes a DOI from a potentially messy input string.
    Handles URLs, prefixes, and whitespace.
    """
    if not input_string:
        return None
        
    s = input_string.strip()
    
    # 1. URL Decoding (in case of encoded chars)
    try:
        from urllib.parse import unquote
        s = unquote(s)
    except:
        pass
        
    # 2. Regex to find the DOI pattern
    # Looks for '10.' followed by 4+ digits, a slash, and then non-whitespace chars
    # This captures standard DOIs like 10.1000/xyz
    doi_regex = r'(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)'
    
    match = re.search(doi_regex, s)
    if match:
        raw_doi = match.group(1)
        # Remove trailing punctuation
        raw_doi = raw_doi.rstrip('.,;)')
        return raw_doi
    
    return None

def get_ids_from_pmc_converter(doi):
    """
    Uses NCBI PMC ID Converter API to translate DOI to PMID and PMCID.
    """
    url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
    params = {
        "tool": "dome_copilot",
        "email": "example@example.com",
        "ids": doi,
        "format": "json"
    }
    
    ids = {"pmid": "", "pmcid": ""}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            records = data.get('records', [])
            if records:
                record = records[0]
                ids['pmid'] = record.get('pmid', '')
                ids['pmcid'] = record.get('pmcid', '')
    except Exception as e:
        print(f"Warning: PMC ID Converter failed for DOI {doi}: {e}")
        
    return ids

def get_crossref_metadata(doi):
    """
    Fetches publication metadata from CrossRef using the DOI.
    """
    # CrossRef API expects the raw DOI in path
    base_url = f"https://api.crossref.org/works/{doi}"
    try:
        headers = {
            "User-Agent": "DomeCopilotAnalysis/1.0 (mailto:example@example.com)"
        }
        response = requests.get(base_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"  [CrossRef] Failed with status: {response.status_code}")
            return None
            
        data = response.json()
        item = data.get('message', {})
        
        # Title
        title_list = item.get('title', [])
        title = title_list[0] if title_list else ''
        
        # If title is missing, consider this a failed lookup to trigger fallbacks
        if not title:
            print("  [CrossRef] Record found but title is missing. Treating as failure.")
            return None

        # Authors
        authors_list = item.get('author', [])
        formatted_authors = []
        for a in authors_list:
            family = a.get('family', '')
            given = a.get('given', '')
            if family or given:
                formatted_authors.append(f"{family} {given}".strip())
        authors = ", ".join(formatted_authors)
        
        # Journal / Container
        journal = ''
        container_title = item.get('container-title', [])
        if container_title:
            journal = container_title[0]
        
        # Check institution logic for Preprints (BioRxiv vs MedRxiv distinction)
        # CrossRef often puts specific preprint server in 'institution' list for CSHL papers
        if not journal:
            institution_list = item.get('institution', [])
            for inst in institution_list:
                name = inst.get('name', '').lower()
                if 'biorxiv' in name:
                    journal = "BioRxiv (Preprint)"
                    break
                elif 'medrxiv' in name:
                    journal = "MedRxiv (Preprint)"
                    break

        # Fallback to Publisher if no specific Journal found so far
        if not journal:
            publisher = item.get('publisher', '')
            if publisher:
                journal = publisher

        # Strict Check: If we have a CSHL DOI (10.1101) but still only have generic 
        # "Cold Spring Harbor Laboratory" as journal/publisher, we should FAIL (return None)
        # to ensure the specific BioRxiv/MedRxiv APIs are called to get the correct source.
        if '10.1101/' in doi:
            if not journal or journal == 'Cold Spring Harbor Laboratory':
                print("  [CrossRef] CSHL DOI found but cannot distinguish BioRxiv/MedRxiv. Falling back to specific APIs.")
                return None
            
        # Year
        year = ''
        date_parts = item.get('published-print', {}).get('date-parts')
        if not date_parts:
             date_parts = item.get('published-online', {}).get('date-parts')
        if not date_parts:
             date_parts = item.get('created', {}).get('date-parts')
             
        if date_parts and len(date_parts) > 0 and len(date_parts[0]) > 0:
            year = str(date_parts[0][0])
            
        return {
            "publication/title": title,
            "publication/authors": authors,
            "publication/journal": journal,
            "publication/year": year,
            "publication/pmid": '',   
            "publication/pmcid": '',  
            "publication/doi": doi
        }
        
    except Exception as e:
        print(f"  [CrossRef] Error: {e}")
        return None

def parse_zenodo_record(record, source_doi):
    """
    Parses a single Zenodo record object into the standard metadata format.
    """
    item = record.get('metadata', {})
    
    # Extract authors
    authors_list = item.get('creators', [])
    authors = ", ".join([a.get('name', '') for a in authors_list])
    
    # Extract Year
    pub_date = item.get('publication_date', '')
    year = pub_date.split('-')[0] if pub_date else ''
    
    return {
        "publication/title": item.get('title', ''),
        "publication/authors": authors,
        "publication/journal": "Zenodo",
        "publication/year": year,
        "publication/pmid": '',
        "publication/pmcid": '',
        "publication/doi": source_doi
    }

def get_zenodo_metadata(doi):
    """
    Fetches metadata from Zenodo using the DOI.
    Strategies:
    1. Direct ID lookup if DOI matches '10.5281/zenodo.<ID>'
    2. Search API with loose query
    3. Search API with strict DOI query
    """
    
    # Strategy 1: Direct ID lookup
    # This is the most reliable method for Zenodo-minted DOIs
    zenodo_pattern = r'10\.5281/zenodo\.(\d+)'
    match = re.search(zenodo_pattern, doi)
    
    if match:
        record_id = match.group(1)
        direct_url = f"https://zenodo.org/api/records/{record_id}"
        print(f"  [Zenodo] Detected Zenodo DOI. Trying direct record lookup: {direct_url}")
        
        try:
            response = requests.get(direct_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return parse_zenodo_record(data, doi)
            elif response.status_code == 404:
                print(f"  [Zenodo] Direct lookup returned 404 (ID might be invalid or restricted). Falling back to search.")
            else:
                print(f"  [Zenodo] Direct lookup failed status: {response.status_code}")
                
        except Exception as e:
            print(f"  [Zenodo] Direct lookup error: {e}")

    # Strategy 2: Search API
    api_url = "https://zenodo.org/api/records"
    
    # First try loose search (just the DOI string). This often handles encoding issues better.
    params = {'q': doi}
    print(f"  [Zenodo] Searching with params: {params}")
    
    try:
        response = requests.get(api_url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            hits = data.get('hits', {}).get('hits', [])
            if hits:
                # Return the first hit
                return parse_zenodo_record(hits[0], doi)
            else:
                # Strategy 3: Strict search if loose search failed
                params['q'] = f'doi:"{doi}"'
                print(f"  [Zenodo] No hits. Retrying with strict query: {params}")
                
                response = requests.get(api_url, params=params, timeout=10)
                if response.status_code == 200:
                    hits = data.get('hits', {}).get('hits', [])
                    if hits:
                        return parse_zenodo_record(hits[0], doi)
                
            print(f"  [Zenodo] No hits found for DOI {doi}")
        else:
            print(f"  [Zenodo] Request failed with status: {response.status_code}")
            
    except Exception as e:
        print(f"  [Zenodo] Error: {e}")
        
    return None

def get_arxiv_id_from_doi(doi):
    """
    Helper to extract strict arXiv ID from DOI if it matches the arXiv DOI pattern (10.48550/...)
    """
    prefix = "10.48550/"
    if doi.startswith(prefix):
        # Strip prefix
        suffix = doi[len(prefix):]
        # Usually format is "arXiv.1234.5678" or "arXiv.quant-ph/0201082" 
        # But sometimes just "1234.5678" if user input was messy but cleaned weirdly
        if suffix.lower().startswith("arxiv."):
            return suffix[6:]
        return suffix
    return None

def get_arxiv_metadata(doi):
    """
    Fetches metadata from arXiv.
    Logic: If DOI is an arXiv DOI, extract ID and search by ID. 
    Otherwise (rare), search by DOI string.
    """
    api_url = "http://export.arxiv.org/api/query"
    
    # PREPARATION: Extract ID if possible
    arxiv_id = get_arxiv_id_from_doi(doi)
    
    if arxiv_id:
        print(f"  [arXiv] Identified valid arXiv DOI. Using ID lookup for: {arxiv_id}")
        params = {"id_list": arxiv_id, "start": 0, "max_results": 1}
    else:
        print(f"  [arXiv] Not a standard 10.48550 DOI. Trying fallback DOI search: {doi}")
        params = {"search_query": f"doi:{doi}", "start": 0, "max_results": 1}
    
    try:
        response = requests.get(api_url, params=params, timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entry = root.find('atom:entry', ns)
            
            if entry is not None:
                # Check for error entry
                id_elem = entry.find('atom:id', ns)
                if id_elem is not None and 'Error' in id_elem.text:
                    print(f"  [arXiv] API returned Error: {entry.find('atom:summary', ns).text}")
                    return None
                    
                title = entry.find('atom:title', ns).text
                title = title.strip().replace('\n', ' ') if title else ''
                
                published = entry.find('atom:published', ns).text
                year = published[:4] if published else ''
                
                authors_list = []
                for author in entry.findall('atom:author', ns):
                    name = author.find('atom:name', ns).text
                    if name:
                        authors_list.append(name)
                authors = ", ".join(authors_list)
                
                return {
                    "publication/title": title,
                    "publication/authors": authors,
                    "publication/journal": "arXiv (Preprint)",
                    "publication/year": year,
                    "publication/pmid": '',
                    "publication/pmcid": '',
                    "publication/doi": doi
                }
            else:
                 print(f"  [arXiv] No entry found in response.")
        else:
             print(f"  [arXiv] Request failed with status: {response.status_code}")

    except Exception as e:
        print(f"  [arXiv] Error: {e}")
    return None

def get_biorxiv_medrxiv_metadata(doi, server):
    """
    Fetches metadata from BioRxiv or MedRxiv using the DOI.
    Server must be 'biorxiv' or 'medrxiv'.
    """
    # PREPARATION: Ensure DOI is clean for path usage. 
    # API: https://api.biorxiv.org/details/[server]/[doi]
    url = f"https://api.biorxiv.org/details/{server}/{doi}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"  [{server}] Request failed with status: {response.status_code}")
            return None
            
        data = response.json()
        messages = data.get('messages', [{}])[0]
        
        if messages.get('status') == 'ok':
            collection = data.get('collection', [])
            if collection:
                item = collection[-1]
                return {
                    "publication/title": item.get('title', ''),
                    "publication/authors": item.get('authors', ''),
                    "publication/journal": f"{server.capitalize()} (Preprint)",
                    "publication/year": item.get('date', '').split('-')[0] if item.get('date') else '',
                    "publication/pmid": '',
                    "publication/pmcid": '',
                    "publication/doi": doi
                }
            else:
                print(f"  [{server}] Response 'ok' but empty collection.")
        else:
             # This is normal if the DOI is not in this server
             print(f"  [{server}] Not found (Status: {messages.get('status')})")
             
    except Exception as e:
        print(f"  [{server}] Error: {e}")
        
    return None

def get_europe_pmc_metadata(pmid, doi):
    """
    Fetches publication metadata from Europe PMC using the PMID.
    """
    if not pmid:
        return None
        
    api_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {'query': f"ext_id:{pmid} src:med", 'format': 'json', 'resultType': 'core'}
    
    try:
        response = requests.get(api_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = data.get('resultList', {}).get('result', [])
        
        if results:
            item = results[0]
            
            author_list = item.get('authorList', {}).get('author', [])
            if author_list:
                authors = ", ".join([f"{a.get('lastName', '')} {a.get('firstName', '')}".strip() for a in author_list])
            else:
                authors = item.get('authorString', '')
                
            return {
                "publication/title": item.get('title', ''),
                "publication/authors": authors,
                "publication/journal": item.get('journalInfo', {}).get('journal', {}).get('title', ''),
                "publication/year": item.get('pubYear', ''),
                "publication/pmid": item.get('pmid', ''),
                "publication/pmcid": item.get('pmcid', ''),
                "publication/doi": doi
            }
        else:
            print(f"  [EuropePMC] No results found for PMID {pmid}")
            
    except Exception as e:
        print(f"  [EuropePMC] Error: {e}")
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python DOI_EPMC_Metadata_to_JSON.py <DOI_STRING>")
        sys.exit(0)
    else:
        raw_input = sys.argv[1]

    print(f"Input: {raw_input}")
    
    # 1. Clean DOI
    doi = clean_and_extract_doi(raw_input)
    if not doi:
        print("Error: Could not extract a valid DOI structure from input.")
        sys.exit(1)
    print(f"Cleaned DOI: {doi}")
    
    # 2. Get Identifiers (PMID/PMCID)
    print("Fetching IDs from PMC Converter...")
    ids = get_ids_from_pmc_converter(doi)
    if ids['pmid']: print(f"  Found PMID: {ids['pmid']}")
    if ids['pmcid']: print(f"  Found PMCID: {ids['pmcid']}")
    
    metadata = None

    # 3. Try CrossRef (Primary)
    print("Attempting CrossRef...")
    metadata = get_crossref_metadata(doi)
    
    # 4. Fallback: Preprints & Zenodo
    if not metadata:
        print("CrossRef failed. Trying fallback sources sequentially...")
        
        # Zenodo
        print("Checking Zenodo...")
        metadata = get_zenodo_metadata(doi)
    
    if not metadata:
        # ArXiv
        print("Checking arXiv...")
        metadata = get_arxiv_metadata(doi)
        
    if not metadata:
        # BioRxiv
        print("Checking BioRxiv...")
        metadata = get_biorxiv_medrxiv_metadata(doi, 'biorxiv')

    if not metadata:
        # MedRxiv
        print("Checking MedRxiv...")
        metadata = get_biorxiv_medrxiv_metadata(doi, 'medrxiv')
    
    # 5. Fallback 2: Europe PMC (via PMID)
    if not metadata and ids['pmid']:
        print(f"Direct DOI lookups failed. Attempting Europe PMC with PMID {ids['pmid']}...")
        metadata = get_europe_pmc_metadata(ids['pmid'], doi)
        
    if not metadata:
        print(f"Error: Could not retrieve metadata for DOI {doi} from any source.")
        sys.exit(1)
        
    # Inject found IDs if missing from source
    if not metadata['publication/pmid'] and ids['pmid']:
        metadata['publication/pmid'] = ids['pmid']
    if not metadata['publication/pmcid'] and ids['pmcid']:
        metadata['publication/pmcid'] = ids['pmcid']

    # 6. Output Result
    print("\n--- Retrieved Metadata ---")
    json_output = json.dumps(metadata, indent=4)
    print(json_output)
    
    # Determine output path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    if metadata.get("publication/pmid"):
        filename = f"metadata_{metadata['publication/pmid']}.json"
    else:
        safe_doi = doi.replace('/', '_')
        filename = f"metadata_doi_{safe_doi}.json"
        
    output_path = os.path.join(script_dir, filename)
    
    with open(output_path, 'w') as f:
        f.write(json_output)
    print(f"\nSaved to file: {output_path}")

if __name__ == "__main__":
    main()
