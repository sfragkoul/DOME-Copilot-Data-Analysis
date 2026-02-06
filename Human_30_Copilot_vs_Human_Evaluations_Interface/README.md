# Human Evaluation Interface (Copilot vs Human)

This directory contains the tools and data for the comparative analysis between DOME Copilot's automated curation and human expert curation.

## Contents

- **`evaluation_app.py`**: A Python application (likely Streamlit or similar dashboard) used to visualize and facilitate the human evaluation process.
- **`Analysis_Evaluation_Results.ipynb`**: A Jupyter Notebook for analyzing the results of the comparison, calculating agreement metrics (precision, recall, F1, Cohen's kappa, etc.).
- **`30_human_evaluation/`**: Directory containing the specific subset of 30 papers selected for detailed human review.
- **`evaluation_results.tsv`**: The recorded results of the evaluation session.

## Purpose

To validate the accuracy of the DOME Copilot, a subset of 30 papers was randomly selected and manually reviewed. This interface supports the workflow of comparing the AI-generated metadata against the ground truth established by human experts.
