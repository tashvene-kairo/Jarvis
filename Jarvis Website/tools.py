from langchain_community.tools import WikipediaQueryRun, DuckDuckGoSearchRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_core.tools import Tool
from datetime import datetime

def save_to_file(content: str, filename: str = "None"):
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"results_{timestamp}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Research paper saved to {filename}")

save_tool = Tool(
    name="SaveToFile",
    func=save_to_file,
    description="Saves the result to a text file.",
)

search = DuckDuckGoSearchRun()
search_tool = Tool(
    name="Search",
    func=search.run,
    description="Search for information across the web.",
)

api_wrapper = WikipediaAPIWrapper(top_k_results=3, doc_content_char_limit=100)
wikipedia_tool = WikipediaQueryRun(api_wrapper=api_wrapper)

