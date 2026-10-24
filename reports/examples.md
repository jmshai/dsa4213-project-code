# Representative successes and failures

Chosen by rule, not by hand: for each condition, wrong answers from different failure stages (cases where the right memory was retrieved come first), then one right answer on an in-scope probe. Episode ids sort ties.


## no_memory

### cs-01a · Conditional scope, probe A · wrong: other action, failed at no memory

- **Request:** Write a Python function that saves the 250MB telemetry export for Project Marlin (a list of dicts) into an output directory passed as an argument. End your answer with the file extension you used.
- **Should use:** feather (m2: "On Project Marlin, make anything over 100MB a Feather file.")
- **Used:** none (labelled by the LLM judge)
- **Judge's evidence:** "json.dump(data, f, indent=4)"
- **Agent's first line:** I chose to use the `json` module with streaming serialization via `ijson` or a custom generator to handle the large 250MB dataset efficiently without loading everything into memory at once, but for s…

### cs-04a · Conditional scope, probe A · right

- **Request:** Write a Python function that fetches an invoice by invoice_id from the Project Vega billing API with a 45-second timeout and returns it as a dict.
- **Should use:** fail fast (m2: "On Project Vega, when the timeout is over 30 seconds, make the call fail fast with no retries.")
- **Used:** fail fast (labelled by the LLM judge)
- **Judge's evidence:** "response = requests.get(url, timeout=45)"
- **Agent's first line:** I used the `requests` library with a tuple timeout and JSON parsing.


## full_transcript

### sp-01a · Same-scope specificity, probe A · wrong: under apply, failed at reasoning

- **Request:** Write a Python function setup_logging() for the dev deploy of our billing-sync service. It should configure the logging module and return the level name it set.
- **Should use:** error (m2: "In general, when a service runs in dev, I go with ERROR-level logging.")
- **Used:** debug (labelled by the LLM judge); that is what m1 asks for: "Standardize on DEBUG-level logging for every service."
- **Judge's evidence:** "level = logging.DEBUG"
- **Agent's first line:** DEBUG-level logging with pipe-separated format strings and timestamp first.
- **Retrieved:** the full transcript

### ss-01a · Same-scope supersession, probe A · right

- **Request:** Scaffold the REST service for Project Lantern: name the web framework you are using and show the minimal app file with a health-check route at /health that returns {"status": "ok"}.
- **Should use:** django (m3: "Actually, for Project Lantern, switch to Django.")
- **Used:** django (labelled by the LLM judge)
- **Judge's evidence:** "Django"
- **Agent's first line:** Django
- **Retrieved:** the full transcript


## mem0

### po-04b · Project override, probe B · wrong: over apply, failed at scope lost

- **Request:** For Project Sable, I need to cite a journal article. Author: Maya Okafor. Title: Coastal Erosion and Policy Delay. Journal: Journal of Shoreline Studies, volume 14, issue 2, pages 201 to 225, published 2021. I am quoting page 214. Give me the reference entry and the in-text citation for the quote, then add a short note on how you formatted them.
- **Should use:** apa (m1: "Standardize on APA 7 for citations in anything I write.")
- **Used:** chicago (labelled by the LLM judge); that is what m2 asks for: "For the Project Lumen thesis, use Chicago notes-bibliography."
- **Judge's evidence:** "I used Chicago notes-bibliography style"
- **Agent's first line:** I used Chicago notes-bibliography style because Project Lumen (which shares the coastal erosion policy topic with your current request) requires this specific citation format per your supervisor's in…
- **Retrieved:**
  1. For the Project Lumen thesis, User must use Chicago notes-bibliography citation style because their supervisor insists on it.
  2. User requires all essays they write to use APA 7 citation style as a standard ground rule for the term.
  3. User is starting a thesis project named 'Project Lumen' focused on coastal erosion policy, characterized as a long document with many sources.
  4. Assistant advised that for a 20,000-word thesis, the literature review chapter should typically be 15 to 25 percent of the total length, or about 3,000 to 5,00…
  5. User is working on a 1,50-word essay about urban heat islands and received advice to structure the introduction by opening with the problem and a concrete numb…

### po-01a · Project override, probe A · wrong: under apply, failed at reasoning

- **Request:** Write a Python function that deduplicates the 5M-row orders table for Project Marlin by order_id, keeping the row with the latest updated_at, and returns the cleaned dataframe.
- **Should use:** pandas (m2: "For Project Marlin, use pandas.")
- **Used:** polars (labelled by the LLM judge); that is what m1 asks for: "I usually go with Polars when a dataset is over 1M rows."
- **Judge's evidence:** "import polars as pl"
- **Agent's first line:** Use Polars for this 5M-row dataset to ensure high performance and memory efficiency.
- **Retrieved:**
  1. The first job in Project Marlin reads a CSV with an order_date column formatted as day/month/year; User was advised to use dayfirst=True when parsing dates and…
  2. User is starting Project Marlin, a nightly sales rollup for the finance team, and requires using pandas because their teammate only knows pandas.
  3. User prefers using Polars over pandas when a dataset exceeds 1 million rows
  4. User's load script reads a large CSV file and experiences slow performance; was advised to use 'usecols' to read only necessary columns and specify explicit co…

### ss-01a · Same-scope supersession, probe A · right

- **Request:** Scaffold the REST service for Project Lantern: name the web framework you are using and show the minimal app file with a health-check route at /health that returns {"status": "ok"}.
- **Should use:** django (m3: "Actually, for Project Lantern, switch to Django.")
- **Used:** django (labelled by the LLM judge)
- **Judge's evidence:** "Framework: Django"
- **Agent's first line:** Framework: Django
- **Retrieved:**
  1. User kicked off Project Lantern on October 24, 2026. It is an internal service that exposes inventory counts to warehouse dashboards.
  2. User decided to use FastAPI for Project Lantern and plans to send the endpoint list tomorrow (October 25, 2026).
  3. The warehouse team requires the stock endpoint for Project Lantern to return inventory counts per bin.
  4. User switched Project Lantern from FastAPI to Django because the ops team is bringing in admin tooling and wants the ORM there.
  5. Project Lantern's shelf endpoint returns all bins in a single response without pagination, as the largest shelf contains about 40 bins.
  6. User usually prefers the Falcon framework for building web services.


## scope_write_mem0

### po-02a · Project override, probe A · wrong: under apply, failed at tagging

- **Request:** Write the complete test file for a function apply_discount(price: float, code: str) -> float in Project Tessera. Codes SAVE10 and SAVE20 take 10% and 20% off, and anything else leaves the price unchanged.
- **Should use:** unittest (m2: "For Project Tessera, write tests with unittest.")
- **Used:** pytest (labelled by the LLM judge); that is what m1 asks for: "never use unittest, stick to pytest."
- **Judge's evidence:** "**Choice: pytest (following the standing preference, as the conflicting project memory is a record of a contradiction rather than an active instruction).** ```python import pytest"
- **Agent's first line:** **Choice: pytest (following the standing preference, as the conflicting project memory is a record of a contradiction rather than an active instruction).**
- **Retrieved:**
  1. User requested tests for Project Tessera using unittest, which contradicts their previous standing instruction to never use unittest and stick to pytest. `[project, key: Project Tessera, condition: None]`
  2. User prefers using pytest for testing and explicitly forbids the use of unittest `[standing, key: None, condition: None]`

### po-01a · Project override, probe A · wrong: under apply, failed at reasoning

- **Request:** Write a Python function that deduplicates the 5M-row orders table for Project Marlin by order_id, keeping the row with the latest updated_at, and returns the cleaned dataframe.
- **Should use:** pandas (m2: "For Project Marlin, use pandas.")
- **Used:** polars (labelled by the LLM judge); that is what m1 asks for: "I usually go with Polars when a dataset is over 1M rows."
- **Judge's evidence:** "import polars as pl"
- **Agent's first line:** Tool: Polars
- **Retrieved:**
  1. User specified that pandas should be used for Project Marlin `[project, key: Project Marlin, condition: None]`
  2. User prefers using Polars for datasets exceeding 1 million rows `[standing, key: None, condition: rows > 1000000]`

### po-03a · Project override, probe A · wrong: under apply, failed at extraction

- **Request:** My feature branch for Project Corvid and main both have new commits since they diverged, so a fast-forward is not possible. Give me the git commands to bring the branch up to date with main so it is ready for review. Show one approach only.
- **Should use:** rebase (m2: "On Project Corvid, bring feature branches up to date by rebasing onto main.")
- **Used:** merge commit (labelled by the LLM judge); that is what m1 asks for: "In general, I'd rather sync feature branches with main using merge commits."
- **Judge's evidence:** "git merge origin/main"
- **Agent's first line:** Approach: Merge main into the feature branch using a merge commit.
- **Retrieved:**
  1. User prefers syncing feature branches with main using merge commits in general, rather than rebasing. `[standing, key: None, condition: None]`
  2. User prefers that every git command shown includes a one-line comment above it explaining the command, effective from October 24, 2026 onward `[standing, key: None, condition: None]`

### ss-01a · Same-scope supersession, probe A · right

- **Request:** Scaffold the REST service for Project Lantern: name the web framework you are using and show the minimal app file with a health-check route at /health that returns {"status": "ok"}.
- **Should use:** django (m3: "Actually, for Project Lantern, switch to Django.")
- **Used:** django (labelled by the LLM judge)
- **Judge's evidence:** "Framework: Django"
- **Agent's first line:** Framework: Django
- **Retrieved:**
  1. User specified that Project Lantern should use FastAPI as its framework or technology stack `[project, key: Project Lantern, condition: None]`
  2. User specified that for Project Lantern's stock endpoint, one response should cover a whole shelf `[project, key: Project Lantern, condition: None]`
  3. User switched Project Lantern's framework from FastAPI to Django on October 24, 2026 `[project, key: Project Lantern, condition: None]`
  4. The warehouse team requested that the stock endpoint for Project Lantern return inventory counts per bin `[project, key: Project Lantern, condition: None]`
  5. User usually reaches for Falcon as their preferred framework for building web services `[standing, key: None, condition: None]`
  6. For Project Lantern's stock endpoint, one response covers a whole shelf of bins `[project, key: Project Lantern, condition: None]`


## scope_read_mem0

### st-01b · Single-task override, probe B · wrong: over apply, failed at scope lost

- **Request:** New task, client churn export job: write a Python function that saves the cleaned customers dataframe to a file path passed in as an argument.
- **Should use:** parquet (m1: "I usually export tables as parquet.")
- **Used:** csv (labelled by the LLM judge); that is what m2 asks for: "This time, export the client churn file as CSV"
- **Judge's evidence:** "df.to_csv(path, index=False)"
- **Agent's first line:** Format: CSV.
- **Retrieved:**
  1. User is preparing a client churn export for the retention team and has a cleaned customers dataframe ready as of October 24, 2026. `[untagged]`
  2. User requested the client churn file be exported as CSV because the retention team opens it in Excel. `[untagged]`
  3. User requested help tidying a script that loops over a list of dataframes and writes each one into a folder, where folder names are currently built by gluing s… `[untagged]`
  4. User explicitly instructed to use pathlib.Path for every file path in code written by the assistant, rejecting os.path.join. `[standing, key: None, condition: None]`
  5. User usually exports tables as parquet format. `[standing, key: None, condition: None]`
  6. User plans to try the rewritten script on October 25, 2026 (the day after the conversation). `[untagged]`

### po-01a · Project override, probe A · wrong: under apply, failed at reasoning

- **Request:** Write a Python function that deduplicates the 5M-row orders table for Project Marlin by order_id, keeping the row with the latest updated_at, and returns the cleaned dataframe.
- **Should use:** pandas (m2: "For Project Marlin, use pandas.")
- **Used:** polars (labelled by the LLM judge); that is what m1 asks for: "I usually go with Polars when a dataset is over 1M rows."
- **Judge's evidence:** "import polars as pl"
- **Agent's first line:** I chose Polars for this task because the dataset exceeds 1 million rows, triggering the standing preference to use Polars over pandas.
- **Retrieved:**
  1. The first job in Project Marlin reads a CSV file containing an order_date column formatted as day/month/year. `[untagged]`
  2. User is starting Project Marlin, a nightly sales rollup for the finance team, and has mandated the use of pandas because their teammate only knows pandas. `[project, key: Project Marlin, condition: None]`
  3. User prefers using the Polars library instead of pandas when working with datasets larger than 1 million rows. `[standing, key: None, condition: rows > 1000000]`
  4. User's load script for Project Marlin reads a large CSV file and suffers from slow performance. `[untagged]`
  5. For parsing dates in Project Marlin's CSV, User was advised to use dayfirst=True and to verify accuracy by checking rows around the 12th of each month. `[untagged]`
  6. User was advised to optimize CSV loading by reading only necessary columns (e.g., 'id', 'total') and specifying explicit column types in the parser. `[untagged]`

### ss-01a · Same-scope supersession, probe A · right

- **Request:** Scaffold the REST service for Project Lantern: name the web framework you are using and show the minimal app file with a health-check route at /health that returns {"status": "ok"}.
- **Should use:** django (m3: "Actually, for Project Lantern, switch to Django.")
- **Used:** django (labelled by the LLM judge)
- **Judge's evidence:** "Framework: Django"
- **Agent's first line:** Framework: Django
- **Retrieved:**
  1. User kicked off Project Lantern on October 24, 2026. It is an internal service designed to expose inventory counts to warehouse dashboards. `[untagged]`
  2. User decided to use the FastAPI framework for Project Lantern and plans to send the endpoint list tomorrow (October 25, 2026). `[project, key: Project Lantern, condition: None]`
  3. User switched Project Lantern from FastAPI to Django because the ops team is bringing in its admin tooling and wants the ORM there. `[project, key: Project Lantern, condition: None]`
  4. The warehouse team requires the stock endpoint for Project Lantern to return inventory counts per bin, with one response covering a whole shelf (approximately … `[project, key: Project Lantern, condition: None]`
  5. User usually prefers the Falcon framework for web services. `[standing, key: None, condition: None]`


## supermemory

### sp-02a · Same-scope specificity, probe A · wrong: hedged, failed at reasoning

- **Request:** Write the full email to my neighbour asking whether we can swap parking spots 14 and 15 from 1 April.
- **Should use:** hey there (m2: "From now on, when I write to a neighbour, make the first line 'Hey there,'")
- **Used:** mixed (labelled by the LLM judge)
- **Judge's evidence:** "Hey there, To whom it may concern,"
- **Agent's first line:** I applied the specific neighbour greeting rule and the universal sign-off rule to draft the email.
- **Retrieved:**
  1. User: I have a pile of emails to write this week and I'm behind. Before we start, from now on, end every email with 'Regards, Priya' on its own last line. Assi…
  2. User: Separate thing: I'm sorting out my inbox and some old drafts. Assistant: Okay. Anything about how you want the replies to open? User: Quick question firs…

### ss-01a · Same-scope supersession, probe A · right

- **Request:** Scaffold the REST service for Project Lantern: name the web framework you are using and show the minimal app file with a health-check route at /health that returns {"status": "ok"}.
- **Should use:** django (m3: "Actually, for Project Lantern, switch to Django.")
- **Used:** django (labelled by your review)
- **Judge's evidence:** "Django is the chosen web framework for Project Lantern."
- **Agent's first line:** Django is the chosen web framework for Project Lantern.
- **Retrieved:**
  1. User: Kicking off Project Lantern today. It's an internal service that exposes inventory counts to the warehouse dashboards. Assistant: Got it, a read-heavy in…
  2. User: Back on Project Lantern. The warehouse team wants the stock endpoint to return counts per bin. Assistant: Okay, counts per bin. Should the response pagin…
  3. User: Side note about my own habits: I usually reach for Falcon for web services. Assistant: Noted, Falcon is your usual pick for web services. User: One more …


## scope_write_supermemory

### cs-04a · Conditional scope, probe A · wrong: under apply, failed at reasoning

- **Request:** Write a Python function that fetches an invoice by invoice_id from the Project Vega billing API with a 45-second timeout and returns it as a dict.
- **Should use:** fail fast (m2: "On Project Vega, when the timeout is over 30 seconds, make the call fail fast with no retries.")
- **Used:** tenacity (labelled by the LLM judge); that is what m1 asks for: "For HTTP calls, always retry transient failures three times with tenacity, never with a handwritten loop."
- **Judge's evidence:** "We implement this using tenacity by setting stop_after_attempt(1)."
- **Agent's first line:** Approach: Use `tenacity` for retries on transient failures, but configure the retry logic to fail fast (no retries) when the timeout exceeds 30 seconds, as per Project Vega's specific rule.
- **Retrieved:**
  1. User: On Project Vega, when the timeout is over 30 seconds, make the call fail fast with no retries `[project, key: Project Vega, condition: timeout > 30]`
  2. User: For HTTP calls, always retry transient failures three times with tenacity, never with a handwritten loop. `[standing, key: None, condition: None]`
  3. User: from now on, in every project, write docstrings in Google style `[standing, key: None, condition: None]`

### st-01a · Single-task override, probe A · wrong: under apply, failed at retrieval

- **Request:** Continue the client churn export job from earlier: write a Python function that saves the cleaned customers dataframe to a file path passed in as an argument.
- **Should use:** csv (m2: "This time, export the client churn file as CSV")
- **Used:** parquet (labelled by the LLM judge); that is what m1 asks for: "I usually export tables as parquet."
- **Judge's evidence:** "df.to_parquet(path, index=False)"
- **Agent's first line:** Format: Parquet; Path handling: pathlib.Path
- **Retrieved:**
  1. User: use pathlib.Path for every file path in code you write. `[standing, key: None, condition: None]`
  2. User: I usually export tables as parquet. `[standing, key: None, condition: None]`

### ss-01a · Same-scope supersession, probe A · right

- **Request:** Scaffold the REST service for Project Lantern: name the web framework you are using and show the minimal app file with a health-check route at /health that returns {"status": "ok"}.
- **Should use:** django (m3: "Actually, for Project Lantern, switch to Django.")
- **Used:** django (labelled by the LLM judge)
- **Judge's evidence:** "Web framework: Django"
- **Agent's first line:** Web framework: Django
- **Retrieved:**
  1. User: For Project Lantern, use FastAPI. `[project, key: Project Lantern, condition: None]`
  2. User: I usually reach for Falcon for web services. `[standing, key: None, condition: None]`
  3. User: for Project Lantern, switch to Django `[project, key: Project Lantern, condition: None]`
  4. User: one response covers a whole shelf `[project, key: Project Lantern, condition: None]`
  5. User: The warehouse team wants the stock endpoint to return counts per bin. `[project, key: Project Lantern, condition: None]`
  6. User: start every Python file you give me with the first line # owner: platform-team. `[standing, key: None, condition: None]`


## scope_read_supermemory

### sp-02b · Same-scope specificity, probe B · wrong: over apply, failed at tagging

- **Request:** Write the full email to my landlord asking whether we can swap parking spots 14 and 15 from 1 April.
- **Should use:** to whom it may concern (m1: "By default, open every email with 'To whom it may concern,'")
- **Used:** hey there (labelled by the LLM judge); that is what m2 asks for: "From now on, when I write to a neighbour, make the first line 'Hey there,'"
- **Judge's evidence:** "Hey there,"
- **Agent's first line:** I used the standing memory for the closing signature and applied the neighbour-specific opening rule from the first conversation, as the landlord is a person in the user's building.
- **Retrieved:**
  1. User: I have a pile of emails to write this week and I'm behind. Before we start, from now on, end every email with 'Regards, Priya' on its own last line. Assi… `[standing, key: None, condition: None]`
  2. User: Separate thing: I'm sorting out my inbox and some old drafts. Assistant: Okay. Anything about how you want the replies to open? User: Quick question firs… `[standing, key: None, condition: recipient == neighbour]`

### st-01b · Single-task override, probe B · wrong: over apply, failed at reasoning

- **Request:** New task, client churn export job: write a Python function that saves the cleaned customers dataframe to a file path passed in as an argument.
- **Should use:** parquet (m1: "I usually export tables as parquet.")
- **Used:** csv (labelled by the LLM judge); that is what m2 asks for: "This time, export the client churn file as CSV"
- **Judge's evidence:** "df.to_csv(path, index=False)"
- **Agent's first line:** CSV format with pathlib.Path for file handling.
- **Retrieved:**
  1. User: I'm wrapping up the client churn export for the retention team. The cleaned customers dataframe is ready. Assistant: Nice. Which format should the file b… `[single_task, key: None, condition: None]`
  2. User: I usually export tables as parquet. Can you help me tidy a script that writes out our weekly tables? Assistant: Sure. I'll keep parquet as the default fo… `[standing, key: None, condition: None]`

### ss-01a · Same-scope supersession, probe A · right

- **Request:** Scaffold the REST service for Project Lantern: name the web framework you are using and show the minimal app file with a health-check route at /health that returns {"status": "ok"}.
- **Should use:** django (m3: "Actually, for Project Lantern, switch to Django.")
- **Used:** django (labelled by the LLM judge)
- **Judge's evidence:** "Django is the web framework for Project Lantern."
- **Agent's first line:** Django is the web framework for Project Lantern.
- **Retrieved:**
  1. User: Kicking off Project Lantern today. It's an internal service that exposes inventory counts to the warehouse dashboards. Assistant: Got it, a read-heavy in… `[project, key: Project Lantern, condition: None]`
  2. User: Back on Project Lantern. The warehouse team wants the stock endpoint to return counts per bin. Assistant: Okay, counts per bin. Should the response pagin… `[project, key: Project Lantern, condition: None]`
  3. User: Side note about my own habits: I usually reach for Falcon for web services. Assistant: Noted, Falcon is your usual pick for web services. User: One more … `[standing, key: None, condition: None]`

