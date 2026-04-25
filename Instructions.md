# Bibilographic Data

## Goal
I want to mirror the patent grant and publication bibliographic data bulk data sets on my local workstation. The two datasets should go into a single SQLite database. 

## Script and Cron Job

### Download Scripts
- Create scripts that pulls from the USPTO ODP bulk data repositories for **publications** and **grants**
- Scripts should take a start date and end date as command line parameters
- pub-query.txt has the format for querying the applications/publications database. grant-query.txt has the format for querying the grants database
- Each query will return one or more zip files. I have provided example files
    - ipab20250122_wk04.zip is applications published the week of Jan. 22, 2025 (week 4 of the year)
    - ipgb20251223_wk51.zip is patent grants issued the week fo Dec. 32, 2025 (week 51 of the year)
- Patent publications are available back to 3/15/2001
- Patent grants are available back to 1/1/2001
- When pulling the initial batch, we should probably limit it to about 10 weeks at a time. Much larger downloads than that might cause issues. 

### Processing Scripts
- Once we have a batch pulled, we process it into our database.
- Database should be called "bibliographic_data.db"
- Create a script that ports the data over into the database. Once we have verified a successful port (with no errors), we can delete source data (with a switch -d/--delete-source-data)
- This script should be thorougly tested with a test bed so we are confident it works and is robust.

### Cron Job
- Once we have the initial dataset, we want to run a weekly cron job on Wednesday at 1 am. 
- This will update both databases with the latest publications and grants. 
- Create a simple wrapper script that calls the two base scripts, with the start date and end date being last thursday to this wednesday. That should grab only the most recent publications. 
- Then the script processes the new data into the database and deletes the source files. 
- Keep a detailed, continuous log in the working directory so we have visibility into what has been done. 

## Database Layout
- Design the database to preserve **all** data available in the XML files. 
- Should include at least these tables:
    - publication (for patent publications)
    - grant (for patent grants)
    - inventor (for named inventors)
    - examiner (for patent examiners)
    - attorney_agent_firm (for attorneys/agents/firms listed)
    - assignee (assignees)
    - applicant (applicants after 2013 when we could have corporate applicants)
    - publication_inventor (junction table)
    - publication_assignee (junction table)
    - publication_applicant (junction table)
    - grant_inventor (junction table)
    - grant_assignee (junction table)
    - grant_applicant (junction table)
- Add any fields you need to preserve all available data
- Propose additional tables or any design changes you think are necessary to properly capture the data in a reasonably-normalized form

## Planning
Start in **planning  mode**. Create a detailed plan for all the scripts you will need, and a detailed database layout plan. Do not write any code until the plan has been approved
    

