# PlotGenre user manual

PlotGenre reads the plot of a film and suggests which genres it belongs to, such as Comedy, Horror or Science Fiction. It also shows how sure it is and which words in the plot led it to that answer.

You don't need any technical knowledge to use it. You only need a web browser.

---

## 1. Opening PlotGenre

1. Ask the person who installed PlotGenre to start it. For them, this is one command: `docker compose up -d`.
2. Open your web browser (Chrome, Firefox or Edge) and go to **http://localhost:8080**.
3. Look at the top right corner:
   * **Green dot, "Model ready":** you can start.
   * **Red dot, "Model starting…":** wait about a minute and refresh the page.
   * **Red dot, "Service offline":** PlotGenre is not running. Ask your administrator.

![Start screen](screenshots/01_classify_empty.png)

## 2. Finding the genres of a film

1. Click **Classify a plot** at the top. This page opens by default.
2. Paste or type the plot of the film into the large box. Describe the story: who the characters are, where it happens, what goes wrong. A paragraph or more works best.
   * Want to try it first? Click one of the **examples** under the box ("Haunted lighthouse", "Bank heist", …).
3. Click **Find genres**, or press **Ctrl + Enter**.
4. After a moment the results appear on the right (or below, on a phone).

![A result](screenshots/02_classify_result.png)

## 3. Reading the result

* **Suggested genres:** the coloured labels with a tick (✓) at the top. These are the genres PlotGenre recommends for the film. The percentage tells you how sure it is. Several genres per film is normal. A heist film is often Crime, Thriller and Action at the same time.
* **How sure the model is:** a bar for every one of the 12 genres. Green bars are suggested genres and grey bars are not. The small orange line on each bar marks the point where a genre becomes "suggested".
* **Words that influenced it:** your plot is shown again with some words highlighted. Each highlighted word pushed PlotGenre towards the genre of the **same colour**. For example, "ghost" highlighted in dark red means it pointed towards Horror. Hover over a word to see the genre name.
* The small grey line at the bottom shows which model version answered and how long it took. If you report a problem, include the "Reference" code.

## 4. Messages you may see

| Message | What it means | What to do |
|---|---|---|
| The **Find genres** button is grey | The text is too short | Write at least 5 words. |
| "Short summary (…words): predictions are more reliable with 30+ words." | It worked, but there wasn't much to go on | Add more detail about the story if you can. |
| "The text does not look like English…" | PlotGenre only understands English | Translate the plot to English first. |
| "The prediction service is starting or temporarily unavailable…" | The model is being loaded or updated, which takes a few seconds | Click **Try again** after a few seconds. |
| "Cannot reach PlotGenre…" / "Service offline" | The system is not running | Ask your administrator to start it. |

![Model temporarily unavailable](screenshots/08_error_model_down.png)

## 5. Using PlotGenre on a phone or tablet

The same address works on a phone or tablet connected to the same network. The administrator will give you the computer's address, for example `http://192.168.1.20:8080`. The page rearranges itself for small screens.

![Phone layout](screenshots/07_mobile_result.png)

## 6. Tips for good results

* Describe the **story**, not the cast list or reviews.
* Include key events, places and conflicts ("a ghost haunts the house", "they plan a bank robbery").
* Very short or very unusual descriptions give less certain results. Treat low percentages (below 40%) as hints, not answers.
* PlotGenre knows these 12 genres: Action, Adventure, Comedy, Crime, Drama, Family, Fantasy, Horror, Mystery, Romance, Science Fiction and Thriller.

---

## 7. For administrators and maintainers: the Pipeline page

Click **Pipeline** at the top. This page is for the people who look after PlotGenre.

![Pipeline console](screenshots/04_pipeline_console.png)

* **Summary strip:** whether a run is in progress, which data version is used (v1 = films before 2000, v2 = all films), which model version is live and its quality score, how many runs succeeded or failed, and the latest drift score.
* **Pipeline stages:** the seven steps that prepare the data and train the model. Green means the last run succeeded, red means it failed, and dashed means it hasn't run yet. Hover over a step to see its time and speed.
* **Run pipeline:** re-runs only the steps whose code, data or settings changed. Confirm in the dialog that appears.
* **Retrain with newer films:** switches to data version 2 (all films) and retrains. The new model goes live only if it is at least as good as the current one.
* **Run history:** every run with its trigger (Manual, Drift alert or Terminal), result and duration. Click **Log** to see the console output, which is useful when a run failed.

  ![Run log](screenshots/05_pipeline_run_log.png)
* **Latest reports:** how many plots were processed, processing speed, model quality, response time, and whether the acceptance criteria passed.
* **Live monitoring:** charts from Grafana that refresh every 10 seconds. Click **Open the full dashboard** for all charts.
* **Tools:** links to MLflow (experiments and model versions), Grafana, Prometheus, Alertmanager and the API documentation. In MLflow 3, choose **Model training → Training runs** in the left menu to see the runs.

### Automatic retraining

If the films people submit start to look different from the films the model learned from (data drift), an alert fires and PlotGenre retrains itself. These runs appear in the history as **Drift alert**.

### Going back to the previous model

If a new model behaves badly, run `python scripts/rollback.py` in a terminal. The previous model is live again within about 20 seconds.
