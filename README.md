<div id="top">

<!-- HEADER STYLE: CLASSIC -->
<div align="center">

<img src="readmeai/assets/logos/purple.svg" width="30%" style="position: relative; top: 0; right: 0;" alt="Project Logo"/>

# ❯ Data Observatory - Pipeline Observability

This tool is DOPE

<!-- BADGES -->
<!-- local repository, no metadata badges. -->

Built with the tools and technologies:

<img src="https://img.shields.io/badge/TOML-9C4121.svg?style=default&logo=TOML&logoColor=white" alt="TOML">
<img src="https://img.shields.io/badge/Ruff-D7FF64.svg?style=default&logo=Ruff&logoColor=black" alt="Ruff">
<img src="https://img.shields.io/badge/Pytest-0A9EDC.svg?style=default&logo=Pytest&logoColor=white" alt="Pytest">
<img src="https://img.shields.io/badge/Python-3776AB.svg?style=default&logo=Python&logoColor=white" alt="Python">
<img src="https://img.shields.io/badge/uv-DE5FE9.svg?style=default&logo=uv&logoColor=white" alt="uv">

</div>
<br>

---

## Table of Contents

- [Table of Contents](#table-of-contents)
- [Overview](#overview)
- [Features](#features)
- [Project Structure](#project-structure)
    - [Project Index](#project-index)
- [Getting Started](#getting-started)
    - [Prerequisites](#prerequisites)
    - [Installation](#installation)
    - [Usage](#usage)
    - [Testing](#testing)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## Overview

Introducing **Dope**, a powerful developer tool designed to simplify data pipeline management and provide unparalleled insights into data relationships and transformations.

**Why Dope?**
This project empowers developers to build more transparent, maintainable, and scalable data-driven solutions. The core features include:

- **💡 Graph-based data modeling:** Enables creation and manipulation of complex graph structures, facilitating traversal and analysis of graph data.
- **🔄 Pipeline data ingestion infrastructure:** Provides plugins for loading external data into a graph store, supporting flexible integration with various data sources.
- **🔍 Data lineage management:** Enables tracking of data origins and transformations throughout the system, maintaining data integrity and transparency.
- **📊 Freshness report generation:** Generates reports detailing pipeline staleness across all nodes in the graph store, providing insights into data freshness and potential issues.
- **📈 Interactive visualization:** Generates self-contained HTML files visualizing pipeline lineage and freshness using Cytoscape.js, allowing users to explore the pipeline's structure and identify areas for improvement.

---

## Features

|      | Component       | Details                              |
| :--- | :-------------- | :----------------------------------- |
| ⚙️  | **Architecture**  | <ul><li>Python-based</li><li>Utilizes `pyproject.toml` for configuration</li></ul> |
| 🔩 | **Code Quality**  | <ul><li>Enforces code standards with `ruff` and `mypy`</li><li>Uses `pytest` for testing</li></ul> |
| 📄 | **Documentation** | <ul><li>No explicit documentation framework detected</li><li>License information available in `license` file</li></ul> |
| 🔌 | **Integrations**  | <ul><li>Utilizes `uv.lock` for locking mechanisms</li><li>Integrates with `kuzu` (purpose unclear)</li></ul> |
| 🧩 | **Modularity**    | <ul><li>No explicit modularity framework detected</li><li>Organized using a single `pyproject.toml` file</li></ul> |
| 🧪 | **Testing**       | <ul><li>Uses `pytest` for testing</li><li>No test coverage metrics available</li></ul> |
| ⚡️  | **Performance**   | <ul><li>No explicit performance optimization techniques detected</li><li>Relies on Python's built-in performance features</li></ul> |
| 🛡️ | **Security**      | <ul><li>No explicit security measures detected</li><li>License information available in `license` file</li></ul> |
| 📦 | **Dependencies**  | <ul><li>`pyproject.toml` for configuration</li><li>`uv.lock` for locking mechanisms</li><li>`makefile` for build automation</li></ul> |
| 🚀 | **Scalability**   | <ul><li>No explicit scalability measures detected</li><li>Relies on Python's built-in concurrency features</li></ul> |

---

## Project Structure

```sh
└── /
    ├── LICENSE
    ├── Makefile
    ├── README.md
    ├── data
    │   └── snapshots
    ├── docs
    │   ├── ARCHITECTURE.md
    │   ├── BUILD_DIRECTIVE.md
    │   └── FRESHNESS_RULE.md
    ├── pyproject.toml
    ├── scripts
    │   ├── export_snapshots.py
    │   ├── run_demo.py
    │   └── seed_walk_demo.py
    ├── src
    │   ├── .DS_Store
    │   └── dope
    ├── tests
    │   ├── __init__.py
    │   ├── __pycache__
    │   ├── smoke_test_plugins.py
    │   ├── test_freshness.py
    │   ├── test_graph.py
    │   ├── test_lineage.py
    │   └── test_plugins.py
    └── uv.lock
```

### Project Index

<details open>
	<summary><b><code>/</code></b></summary>
	<!-- __root__ Submodule -->
	<details>
		<summary><b>__root__</b></summary>
		<blockquote>
			<div class='directory-path' style='padding: 8px 0; color: #666;'>
				<code><b>⦿ __root__</b></code>
			<table style='width: 100%; border-collapse: collapse;'>
			<thead>
				<tr style='background-color: #f8f9fa;'>
					<th style='width: 30%; text-align: left; padding: 8px;'>File Name</th>
					<th style='text-align: left; padding: 8px;'>Summary</th>
				</tr>
			</thead>
				<tr style='border-bottom: 1px solid #eee;'>
					<td style='padding: 8px;'><b><a href='/LICENSE'>LICENSE</a></b></td>
					<td style='padding: 8px;'>- Establishes the licensing terms for the entire project, granting users permission to freely use, modify, and distribute the software while requiring attribution and inclusion of the copyright notice<br>- The license ensures that the authors are not liable for any claims or damages arising from the softwares use<br>- It provides a clear framework for collaboration and contribution to the project.</td>
				</tr>
				<tr style='border-bottom: 1px solid #eee;'>
					<td style='padding: 8px;'><b><a href='/Makefile'>Makefile</a></b></td>
					<td style='padding: 8px;'>- Manages project workflows by defining tasks for demonstration, testing, live execution, cleaning, formatting, and linting<br>- Enables developers to execute specific commands to run demos, perform unit tests, clean up generated files, format code, and check for errors<br>- Simplifies the development process by providing a centralized way to control various aspects of the project, ensuring consistency and efficiency across different tasks and environments.</td>
				</tr>
				<tr style='border-bottom: 1px solid #eee;'>
					<td style='padding: 8px;'><b><a href='/pyproject.toml'>pyproject.toml</a></b></td>
					<td style='padding: 8px;'>- Configures the foundation of the Data Observatory project, defining its metadata, dependencies, and build settings<br>- Establishes the projects identity, versioning, and licensing information, while also specifying requirements for Python compatibility and development tools<br>- Additionally, it sets up scripts and build systems, ensuring a solid base for the projects architecture and facilitating efficient development and deployment of pipeline observability features.</td>
				</tr>
			</table>
		</blockquote>
	</details>
	<!-- scripts Submodule -->
	<details>
		<summary><b>scripts</b></summary>
		<blockquote>
			<div class='directory-path' style='padding: 8px 0; color: #666;'>
				<code><b>⦿ scripts</b></code>
			<table style='width: 100%; border-collapse: collapse;'>
			<thead>
				<tr style='background-color: #f8f9fa;'>
					<th style='width: 30%; text-align: left; padding: 8px;'>File Name</th>
					<th style='text-align: left; padding: 8px;'>Summary</th>
				</tr>
			</thead>
				<tr style='border-bottom: 1px solid #eee;'>
					<td style='padding: 8px;'><b><a href='/scripts/run_demo.py'>run_demo.py</a></b></td>
					<td style='padding: 8px;'>- Runs a one-shot demo of the data lineage tool, loading snapshots from Fivetran and dbt, performing seed walks on specified connectors, and generating reports on data freshness and lineage<br>- The demo outputs Cypher queries, tabular freshness reports, and writes HTML and CSV files for visualization and analysis<br>- It provides a comprehensive overview of the data pipelines health and dependencies.</td>
				</tr>
				<tr style='border-bottom: 1px solid #eee;'>
					<td style='padding: 8px;'><b><a href='/scripts/export_snapshots.py'>export_snapshots.py</a></b></td>
					<td style='padding: 8px;'>- Exports live snapshot data from Fivetran and dbt Cloud APIs to a local directory<br>- Requires environment variables for API credentials, which are not configured by default<br>- The script writes exported data to the <code>data/live/</code> directory, including connections, schemas, manifest, and run results<br>- It serves as a critical component in the projects data pipeline, enabling further processing and analysis of live snapshot data.</td>
				</tr>
				<tr style='border-bottom: 1px solid #eee;'>
					<td style='padding: 8px;'><b><a href='/scripts/seed_walk_demo.py'>seed_walk_demo.py</a></b></td>
					<td style='padding: 8px;'>- Demonstrates the core seed walk loop by iterating over all connector IDs, showcasing a 4-line process that loads plugins into a graph, retrieves connector IDs from a snapshot, and performs a seed walk for each ID<br>- The script provides a demo of the dope seed walk functionality, highlighting its ability to traverse lineage nodes and edges across multiple connectors.</td>
				</tr>
			</table>
		</blockquote>
	</details>
	<!-- src Submodule -->
	<details>
		<summary><b>src</b></summary>
		<blockquote>
			<div class='directory-path' style='padding: 8px 0; color: #666;'>
				<code><b>⦿ src</b></code>
			<!-- dope Submodule -->
			<details>
				<summary><b>dope</b></summary>
				<blockquote>
					<div class='directory-path' style='padding: 8px 0; color: #666;'>
						<code><b>⦿ src.dope</b></code>
					<!-- core Submodule -->
					<details>
						<summary><b>core</b></summary>
						<blockquote>
							<div class='directory-path' style='padding: 8px 0; color: #666;'>
								<code><b>⦿ src.dope.core</b></code>
							<table style='width: 100%; border-collapse: collapse;'>
							<thead>
								<tr style='background-color: #f8f9fa;'>
									<th style='width: 30%; text-align: left; padding: 8px;'>File Name</th>
									<th style='text-align: left; padding: 8px;'>Summary</th>
								</tr>
							</thead>
								<tr style='border-bottom: 1px solid #eee;'>
									<td style='padding: 8px;'><b><a href='/src/dope/core/freshness.py'>freshness.py</a></b></td>
									<td style='padding: 8px;'>- Determines pipeline freshness by considering business days and holidays<br>- It calculates the last business day before a given date, checks if a pipeline is stale based on its last run end time, and returns an effective fresh date for a pipeline run<br>- The module provides functions to walk backward from a reference date until a weekday not in holidays is found, ensuring data reflects up-to-date business operations.</td>
								</tr>
								<tr style='border-bottom: 1px solid #eee;'>
									<td style='padding: 8px;'><b><a href='/src/dope/core/graph.py'>graph.py</a></b></td>
									<td style='padding: 8px;'>- Summary<strong>The <code>graph.py</code> file is a core component of the project's architecture, responsible for managing and manipulating graph data structures<br>- It provides a foundation for building, traversing, and analyzing complex relationships between entities within the system.In the context of the larger codebase, this module enables the creation of a robust graph-based framework that can be leveraged by various components to model and interact with intricate networks of data<br>- By abstracting away low-level implementation details, <code>graph.py</code> empowers developers to focus on higher-level logic and domain-specific problem-solving.</strong>Key Achievements<em>*</em> Provides a centralized hub for graph-related functionality<em> Enables the creation and manipulation of complex graph structures</em> Facilitates traversal and analysis of graph dataBy utilizing this module, other components within the project can tap into its capabilities to build sophisticated applications that rely on graph-based modeling and reasoning.</td>
								</tr>
								<tr style='border-bottom: 1px solid #eee;'>
									<td style='padding: 8px;'><b><a href='/src/dope/core/kuzu_backend.py'>kuzu_backend.py</a></b></td>
									<td style='padding: 8px;'>- Provides a Kùzu graph backend implementation, enabling the creation of on-disk or in-memory databases<br>- It offers methods for adding nodes and edges, executing Cypher queries, and saving/loading databases<br>- The code ensures compatibility with the GraphStore API and handles cases where Kùzu is not installed<br>- A factory function allows users to select between different backends, including PurePyGraph and Kùzu.</td>
								</tr>
								<tr style='border-bottom: 1px solid #eee;'>
									<td style='padding: 8px;'><b><a href='/src/dope/core/plugin.py'>plugin.py</a></b></td>
									<td style='padding: 8px;'>- Provides pipeline data ingestion infrastructure through plugins that load external data into a graph store<br>- PipelinePlugin subclasses implement the ingest method to fetch data from sources like APIs or manifest files, supporting both full reload and incremental updates<br>- The plugin architecture enables flexible integration with various data sources, allowing for seamless data population and management within the pipeline.</td>
								</tr>
								<tr style='border-bottom: 1px solid #eee;'>
									<td style='padding: 8px;'><b><a href='/src/dope/core/schema.py'>schema.py</a></b></td>
									<td style='padding: 8px;'>- Defines the core schema of the data catalog, outlining node types and relationships between them<br>- It establishes a standardized structure for representing Fivetran connections, Snowflake tables, dbt models and tests, and data products, enabling the creation of a comprehensive graph database that captures dependencies and lineage across these entities<br>- This schema serves as the foundation for data discovery, governance, and analytics within the larger architecture.</td>
								</tr>
							</table>
						</blockquote>
					</details>
					<!-- plugins Submodule -->
					<details>
						<summary><b>plugins</b></summary>
						<blockquote>
							<div class='directory-path' style='padding: 8px 0; color: #666;'>
								<code><b>⦿ src.dope.plugins</b></code>
							<table style='width: 100%; border-collapse: collapse;'>
							<thead>
								<tr style='background-color: #f8f9fa;'>
									<th style='width: 30%; text-align: left; padding: 8px;'>File Name</th>
									<th style='text-align: left; padding: 8px;'>Summary</th>
								</tr>
							</thead>
								<tr style='border-bottom: 1px solid #eee;'>
									<td style='padding: 8px;'><b><a href='/src/dope/plugins/dbt.py'>dbt.py</a></b></td>
									<td style='padding: 8px;'>- Summary**The <code>dbt.py</code> file is a plugin for the Dope project, responsible for ingesting data from dbt (data build tool) into the graph<br>- Its primary purpose is to collect and process manifest and run-result data from dbt, making it available for further analysis and visualization within the Dope ecosystem.In the context of the entire codebase architecture, this plugin serves as a critical component for integrating dbt data sources with the Dope platform, enabling users to leverage the power of dbts data transformation capabilities alongside Dope's graph-based insights<br>- By ingesting dbt data, this plugin facilitates a more comprehensive understanding of data pipelines and workflows, ultimately enhancing the overall value proposition of the Dope project.</td>
								</tr>
								<tr style='border-bottom: 1px solid #eee;'>
									<td style='padding: 8px;'><b><a href='/src/dope/plugins/fivetran.py'>fivetran.py</a></b></td>
									<td style='padding: 8px;'>- Ingests Fivetran connector metadata into a graph store, supporting snapshot and live ingestion modes<br>- Reads CSV files from a snapshot directory or queries the Fivetran REST API to populate the graph with FIVETRAN_CONNECTION and SNOWFLAKE_TABLE nodes, as well as SYNC_TO edges<br>- Handles data freshness and staleness, creating a comprehensive representation of Fivetran connector metadata in the graph store.</td>
								</tr>
							</table>
						</blockquote>
					</details>
					<!-- cli Submodule -->
					<details>
						<summary><b>cli</b></summary>
						<blockquote>
							<div class='directory-path' style='padding: 8px 0; color: #666;'>
								<code><b>⦿ src.dope.cli</b></code>
							<table style='width: 100%; border-collapse: collapse;'>
							<thead>
								<tr style='background-color: #f8f9fa;'>
									<th style='width: 30%; text-align: left; padding: 8px;'>File Name</th>
									<th style='text-align: left; padding: 8px;'>Summary</th>
								</tr>
							</thead>
								<tr style='border-bottom: 1px solid #eee;'>
									<td style='padding: 8px;'><b><a href='/src/dope/cli/main.py'>main.py</a></b></td>
									<td style='padding: 8px;'>- Summary<strong>The <code>main.py</code> file serves as the entry point for the Command-Line Interface (CLI) of the Dope project<br>- Its primary purpose is to provide a user-friendly interface for interacting with the project's core functionality, allowing users to execute various commands and operations.In the context of the entire codebase architecture, this file acts as a bridge between the user and the underlying system, enabling seamless communication and control<br>- By leveraging this CLI, users can harness the full potential of the Dope project without needing to delve into the technical intricacies of the implementation.</strong>Key Achievements<em>*</em> Provides a user-friendly interface for interacting with the project's core functionality<em> Enables execution of various commands and operations</em> Acts as a bridge between the user and the underlying systemBy using this CLI, users can efficiently utilize the Dope projects capabilities, making it an essential component of the overall codebase architecture.</td>
								</tr>
							</table>
						</blockquote>
					</details>
					<!-- query Submodule -->
					<details>
						<summary><b>query</b></summary>
						<blockquote>
							<div class='directory-path' style='padding: 8px 0; color: #666;'>
								<code><b>⦿ src.dope.query</b></code>
							<table style='width: 100%; border-collapse: collapse;'>
							<thead>
								<tr style='background-color: #f8f9fa;'>
									<th style='width: 30%; text-align: left; padding: 8px;'>File Name</th>
									<th style='text-align: left; padding: 8px;'>Summary</th>
								</tr>
							</thead>
								<tr style='border-bottom: 1px solid #eee;'>
									<td style='padding: 8px;'><b><a href='/src/dope/query/freshness_report.py'>freshness_report.py</a></b></td>
									<td style='padding: 8px;'>- Generates a freshness report detailing pipeline staleness across all nodes in the graph store<br>- The report groups nodes by type and provides a tabular view of each nodes freshness status, including last run end time, staleness flag, and row count<br>- The report is exported to a CSV file for further analysis, offering insights into data freshness and potential issues within the pipeline.</td>
								</tr>
								<tr style='border-bottom: 1px solid #eee;'>
									<td style='padding: 8px;'><b><a href='/src/dope/query/lineage.py'>lineage.py</a></b></td>
									<td style='padding: 8px;'>- Summary**The <code>lineage.py</code> file is a crucial component of the Dope project's query module<br>- Its primary purpose is to manage and resolve data lineage, enabling the tracking of data origins and transformations throughout the system<br>- This module plays a vital role in maintaining data integrity, transparency, and accountability within the larger codebase architecture.In essence, this code facilitates the creation of a data provenance graph, allowing users to understand how data has been processed, transformed, and related to other data entities<br>- By doing so, it provides a foundation for auditing, debugging, and optimizing data workflows, ultimately contributing to the overall reliability and trustworthiness of the Dope system.By incorporating this module, developers can ensure that their applications are equipped with robust data lineage capabilities, enabling them to build more transparent, maintainable, and scalable data-driven solutions.</td>
								</tr>
								<tr style='border-bottom: 1px solid #eee;'>
									<td style='padding: 8px;'><b><a href='/src/dope/query/viz.py'>viz.py</a></b></td>
									<td style='padding: 8px;'>- Generates a self-contained HTML file visualizing pipeline lineage and freshness using Cytoscape.js<br>- It takes seed walk results as input and produces an interactive graph displaying nodes, edges, and their relationships<br>- The visualization highlights fresh and stale data, allowing users to explore the pipelines structure and identify areas for improvement<br>- The output is a standalone HTML file that can be shared or embedded in other applications.</td>
								</tr>
							</table>
						</blockquote>
					</details>
				</blockquote>
			</details>
		</blockquote>
	</details>
</details>

---

## Getting Started

### Prerequisites

This project requires the following dependencies:

- **Programming Language:** Python
- **Package Manager:** Uv

### Installation

Build  from the source and intsall dependencies:

1. **Clone the repository:**

    ```sh
    ❯ git clone ../
    ```

2. **Navigate to the project directory:**

    ```sh
    ❯ cd 
    ```

3. **Install the dependencies:**

<!-- SHIELDS BADGE CURRENTLY DISABLED -->
	<!-- [![uv][uv-shield]][uv-link] -->
	<!-- REFERENCE LINKS -->
	<!-- [uv-shield]: https://img.shields.io/badge/uv-DE5FE9.svg?style=for-the-badge&logo=uv&logoColor=white -->
	<!-- [uv-link]: https://docs.astral.sh/uv/ -->

	**Using [uv](https://docs.astral.sh/uv/):**

	```sh
	❯ uv sync --all-extras --dev
	```

### Usage

Run the project with:

**Using [uv](https://docs.astral.sh/uv/):**
```sh
uv run python {entrypoint}
```

### Testing

 uses the {__test_framework__} test framework. Run the test suite with:

**Using [uv](https://docs.astral.sh/uv/):**
```sh
uv run pytest tests/
```

---

## License

 is protected under the [MIT LICENSE](https://choosealicense.com/licenses) License. For more details, refer to the [LICENSE](https://choosealicense.com/licenses/) file.

---


<div align="right">

[![][back-to-top]](#top)

</div>


[back-to-top]: https://img.shields.io/badge/-BACK_TO_TOP-151515?style=flat-square


---
