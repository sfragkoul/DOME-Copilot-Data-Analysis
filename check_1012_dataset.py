import os

def check_1012_dataset():
    base_dir = "Download_1012_Positive_PMC_Full_Text_and_Supplementary"
    supp_dir = os.path.join(base_dir, "Positive_PMC_Supplementary")
    pdf_dir = os.path.join(base_dir, "Positive_PMC_PDFs")

    print(f"Checking dataset in: {base_dir}")

    # 1. Check Supplementary Folders
    supp_pmcids = set()
    if os.path.exists(supp_dir):
        items = os.listdir(supp_dir)
        for item in items:
            if os.path.isdir(os.path.join(supp_dir, item)):
                supp_pmcids.add(item)
        print(f"Total folders in 'Positive_PMC_Supplementary': {len(supp_pmcids)}")
    else:
        print(f"Directory not found: {supp_dir}")

    # 2. Check PDFs
    pdf_pmcids = set()
    if os.path.exists(pdf_dir):
        items = os.listdir(pdf_dir)
        for item in items:
            if item.lower().endswith('.pdf'):
                # Extract PMCID. Usually 'PMCxxx_main.pdf' or 'PMCxxx.pdf'
                if '_main' in item:
                    pmcid = item.split('_main')[0]
                else:
                    pmcid = os.path.splitext(item)[0]
                pdf_pmcids.add(pmcid)
        print(f"Total PDF files in 'Positive_PMC_PDFs': {len(pdf_pmcids)}")
    else:
        print(f"Directory not found: {pdf_dir}")

    # 3. Direct Check: PDF PMCIDs matching Supplementary PMCIDs
    print("\n--- Matching Check ---")
    
    # Intersection
    matches = pdf_pmcids.intersection(supp_pmcids)
    
    # Missing in Supp (Present in PDF but no folder)
    pdfs_without_folder = pdf_pmcids - supp_pmcids
    
    # Missing in PDF (Present in Folder but no main PDF)
    folders_without_pdf = supp_pmcids - pdf_pmcids

    print(f"Matches (PMCID in both PDF list and Folder list): {len(matches)}")

    if pdfs_without_folder:
        print(f"\nWARNING: {len(pdfs_without_folder)} PDFs do not have a corresponding Supplementary folder:")
        # Print first 10
        sorted_list = sorted(list(pdfs_without_folder))
        print(", ".join(sorted_list[:10]) + ("..." if len(sorted_list) > 10 else ""))
    else:
        print("\nAll PDFs have a corresponding Supplementary folder.")

    if folders_without_pdf:
        print(f"\nWARNING: {len(folders_without_pdf)} Supplementary folders do not have a corresponding PDF file:")
        # Print first 10
        sorted_list = sorted(list(folders_without_pdf))
        print(", ".join(sorted_list[:10]) + ("..." if len(sorted_list) > 10 else ""))
    else:
        print("\nAll Supplementary folders have a corresponding PDF file.")

if __name__ == "__main__":
    check_1012_dataset()
