# PaperPort

PaperPort is a Streamlit web app that helps students download and merge CAIE past papers faster.

Instead of searching for papers one by one, downloading each file manually, and then merging them yourself, this app lets you choose your subject, years, sessions, and paper numbers in one place. It then downloads the matching PDFs, merges them, and gives you a ZIP file with the finished results.

## Why I Made This

This project came from a real problem.

When revising for exams, it can be frustrating to collect past papers manually. Usually the process looks like this:

- Search for one paper
- Download it
- Search for the next one
- Download that too
- Repeat again and again
- Open another tool to merge the PDFs

That takes a lot of time, especially when you want many years, different sessions, and multiple paper variants.

The inspiration for PaperPort came from the difficulty of:

- Downloading past papers individually
- Keeping files organized
- Merging large numbers of PDFs by hand
- Repeating the same boring process every time you study

I wanted a simple tool that could save time and make revision easier. So PaperPort was built to automate that whole process.

## What PaperPort Does

PaperPort helps you:

- Choose between IGCSE and A Level subjects
- Select a subject from a list
- Pick a start year and end year
- Choose sessions like `m`, `s`, and `w`
- Select the paper type:
  - `qp` for Question Papers
  - `ms` for Mark Schemes
  - `in` for Inserts
  - `gt` for Grade Thresholds
- Enter paper numbers such as `12`, `22`, `32`, or `42`
- Optionally upload your own PNG cover image
- Automatically merge the downloaded PDFs
- Add a front cover and back page to the final merged files
- Download everything as a ZIP file

## How It Works

The app follows a simple flow:

1. You choose the exam level, subject, years, sessions, and paper type.
2. The app builds the expected CAIE filenames.
3. It downloads matching PDFs from the source website.
4. It groups papers by paper number.
5. It creates a merged PDF for each paper number.
6. It adds a cover page at the front.
7. It adds the ending page at the back.
8. It places all merged files into a ZIP download.

## Features

- Simple Streamlit interface
- Fast multithreaded downloading
- Automatic PDF merging
- Optional custom cover image upload
- Built-in front cover and back page support
- Download tracking with `data.json`
- Works on Windows, macOS, and Linux

## Project Files

Here is a simple explanation of the main files:

- [mainweb.py](/C:/Users/Fernando/Desktop/PPV2/ComplieYourPapers-main/mainweb.py)
  The main Streamlit application.

- [requirements.txt](/C:/Users/Fernando/Desktop/PPV2/ComplieYourPapers-main/requirements.txt)
  The Python packages needed for the project.

- [data.json](/C:/Users/Fernando/Desktop/PPV2/ComplieYourPapers-main/data.json)
  Stores download statistics and logs.

- [template_base.png](/C:/Users/Fernando/Desktop/PPV2/ComplieYourPapers-main/template_base.png)
  Default background used for the front cover.

- [end.pdf](/C:/Users/Fernando/Desktop/PPV2/ComplieYourPapers-main/end.pdf)
  PDF added to the end of merged files as the back page.

- [Poppins-Bold.ttf](/C:/Users/Fernando/Desktop/PPV2/ComplieYourPapers-main/Poppins-Bold.ttf)
  Font used when generating the cover.

- [.streamlit/config.toml](/C:/Users/Fernando/Desktop/PPV2/ComplieYourPapers-main/.streamlit/config.toml)
  Streamlit theme and UI settings.

## Requirements

Before running the project, make sure you have:

- Python 3.10 or newer
- Internet connection
- `pip` installed

## Installation

Open a terminal in the project folder and run:

```bash
pip install -r requirements.txt
```

## How To Run

Start the app with:

```bash
streamlit run mainweb.py
```

After that, Streamlit will show a local link in the terminal, usually:

```text
http://localhost:8501
```

Open that link in your browser.

## How To Use

1. Select the level: `IGCSE` or `A Level`
2. Choose your subject
3. Pick the start year and end year
4. Choose the session or sessions you want
5. Select the paper type
6. Enter paper numbers if needed
7. Upload a PNG cover image if you want a custom front page
8. Click the download button
9. Wait for the app to download and merge the PDFs
10. Download the final ZIP file

## Example

If you want:

- IGCSE
- Mathematics
- Years `2020` to `2023`
- Sessions `m`, `s`, and `w`
- Question papers
- Paper numbers `12 22 32 42`

PaperPort will try to download all matching PDFs, merge them by paper number, add the front and back pages, and give you the finished files in one ZIP.

## Who This Is For

This project is useful for:

- Students revising for CAIE exams
- Teachers collecting practice material
- Anyone who is tired of downloading papers one at a time

## Problem It Solves

Without this app, students often have to:

- Visit websites repeatedly
- Download papers individually
- Rename or organize files manually
- Use a separate PDF merger
- Waste time on setup instead of revision

PaperPort reduces that manual work so you can focus more on studying.

## Future Ideas

Possible improvements for the future:

- Better error messages for missing papers
- More exam boards
- More cover design options
- Filters for specific variants
- Save recent searches
- Better mobile layout

## Author

Fernando Gabriel Morera

## License

This project is licensed under the [LICENSE](/C:/Users/Fernando/Desktop/PPV2/ComplieYourPapers-main/LICENSE) file in this repository.
