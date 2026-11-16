# Evidence for the two failure types

Checked on 16 Nov 2026 against the live site and the files in this folder.

## 1. Star ratings

The site shows the rating only as a CSS class on an icon row, for example on
[Shakespeare's Sonnets](https://books.toscrape.com/catalogue/shakespeares-sonnets_989/index.html):

```html
<p class="star-rating Four">
```

With an OpenAI model, ScrapeGraphAI 2.1.4 turns an HTML source into Markdown before the model sees it (`FetchNode` calls `convert_to_md`, which uses html2text). Running that same function on the page above gives, right after the stock line:

```
__In stock (19 available)

__________

* * *

**Warning!** This is a demo website for web scraping purposes. Prices and ratings here were randomly assigned and have no real meaning.
```

The icon row becomes a line of underscores and the class (`Four`) is gone; the words "star" and "rating" appear only in the site's warning banner. So the model receives no rating, and its answers (mostly 3, see `results.json`) cannot come from the page. This shows where the information is lost; it does not show how the model chose its numbers.

## 2. Descriptions

Literal comparison: 2 of 19 descriptions match the reference exactly; the result is the same after collapsing whitespace. For the other 17, a character-level diff of `reference_books.json` against `raw_llm_output.json` shows:

- **16 pages:** the model left out a passage of about 375 characters. On the site that passage really is printed twice: the description paragraph of [A Light in the Attic](https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html) contains "It's hard to imagine a world without A Light in the Attic" two times.
- **17 pages:** the model left out the trailing "...more" that is part of the paragraph on the site.
- **9 pages:** small edits: missing spaces inserted after full stops ("weather.Detroit" → "weather. Detroit"), apostrophes "corrected" ("Yeat's" → "Yeats's", "Jess'" → "Jess's"), one straight apostrophe replaced with a curly one.

The cleaned text may read better, but it is no longer what the site says, and the output gives no sign that anything was changed.
