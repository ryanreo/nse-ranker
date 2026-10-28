const VIDEO = {
  title: "Briefing: your watchlist file",
  scenes: [
    {
      label: "What we're building",
      say: [
        "Section two turns our research into a file the program can read.",
        "It holds all seventy two stocks from your heatmap, with each one's sector, type and status.",
        "Every later part of the ranker starts from this list."
      ],
      html: `<p class="big s">Your watchlist file</p>
             <p class="mid s">72 stocks: sector, type, status</p>
             <p class="sub s">Prices, news and scores all start from this list</p>`
    },
    {
      label: "The plan",
      say: [
        "There are three parts.",
        "First, watchlist dot toml, a plain text file that lists every stock.",
        "Second, watchlist dot py, which reads that file into Python.",
        "Third, a command that prints a summary, so we can see it worked."
      ],
      html: `<p class="mid s">Three parts</p>
             <div class="grid">
               <div class="card teal s"><b>1. watchlist.toml</b>One block per stock, easy to read and edit</div>
               <div class="card green s"><b>2. watchlist.py</b>Loads the file into a list of dictionaries</div>
               <div class="card amber s"><b>3. python -m nse_ranker watchlist</b>Prints counts and the table</div>
             </div>`
    },
    {
      label: "Key new idea: a list of dictionaries",
      say: [
        "The key new idea is a list of dictionaries.",
        "Each stock is a dictionary: labels like ticker and status, each with a value.",
        "Put all the stocks in a list, and a for loop can visit them one at a time.",
        "Here we loop over two fruits and print each one's name and price."
      ],
      html: `<p class="mid s">A list of dictionaries</p>
             <p class="sub s">Like a stack of index cards: same labels on every card</p>
             <p class="sub s">One card = one dictionary. The stack = the list.</p>
             <div class="code s" data-type="fruits = [
    {&quot;name&quot;: &quot;mango&quot;, &quot;price&quot;: 50},
    {&quot;name&quot;: &quot;banana&quot;, &quot;price&quot;: 10},
]
for fruit in fruits:
    print(fruit[&quot;name&quot;], fruit[&quot;price&quot;])"></div>`
    },
    {
      label: "Watch out for",
      say: [
        "Watch out: text must match exactly. Rank with a capital R is not the same as rank.",
        "A missing label crashes square brackets. The get method returns None instead.",
        "And two stocks, ALP and TRFC, are priced in US dollars, not shillings. The file marks their currency."
      ],
      html: `<div class="grid">
               <div class="card coral s"><b>"Rank" ≠ "rank"</b>Comparisons are exact, capitals included</div>
               <div class="card amber s"><b>card["x"] vs card.get("x")</b>Brackets crash on a missing label; .get gives None</div>
               <div class="card purple s"><b>USD counters</b>ALP and TRFC have currency = "USD"</div>
             </div>`
    },
    {
      label: "Tips",
      say: [
        "Tip one: open the toml file and read a few stocks. It's just text.",
        "Tip two: print one dictionary to see exactly what labels it has.",
        "Tip three: run the tests. They tell you straight away if your function works."
      ],
      html: `<div class="grid">
               <div class="card green s"><b>Read the data</b>watchlist.toml is plain text</div>
               <div class="card teal s"><b>Print to see</b>print(stocks[0]) shows one card</div>
               <div class="card purple s"><b>Run the tests</b><span style="font-family:ui-monospace,Consolas,monospace">python -m unittest</span></div>
             </div>`
    },
    {
      label: "Your mission",
      say: [
        "Your mission is one small function called rankable.",
        "It gets the list of stocks and returns a new list with only the stocks whose status is rank.",
        "Open watchlist dot py, find the to do, and use a for loop with an if. When it works, the summary shows fifty two rankable stocks."
      ],
      html: `<p class="big s">Your mission</p>
             <p class="mid s">rankable(stocks) → only status "rank"</p>
             <p class="sub s">In nse_ranker/watchlist.py, find # TODO. Goal: 52 stocks.</p>`
    }
  ]
};
