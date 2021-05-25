import importlib, sys, argparse, os
from typing import List, Dict, Tuple
import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

import switch_model.solve
from switch_model.utilities import query_yes_no, StepTimer

original_working_dir = os.getcwd()


class GraphDataFolder:
    OUTPUTS = "outputs"
    INPUTS = "inputs"


class Scenario:
    """
    Stores the information related to a scenario such as the scenario name (used while graphing)
    and the scenario path.

    Also allows doing:

    with scenario:
        # some operation

    Here, some operation will be run as if the working directory were the directory of the scenario
    """

    root_path = os.getcwd()

    def __init__(self, rel_path, name=None):
        self.path = os.path.join(Scenario.root_path, rel_path)
        self.name = name

        if not os.path.isdir(self.path):
            raise Exception(f"Directory does not exist: {self.path}")

    def __enter__(self):
        os.chdir(self.path)

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.chdir(Scenario.root_path)


class GraphData:
    """
    Object that stores and handles loading csv into dataframes data for different scenarios.
    """

    def __init__(self, scenarios: List[Scenario]):
        self.scenarios: List[Scenario] = scenarios

        # Here we store a mapping of csv file names to their dataframes.
        # Each dataframe has a column called 'scenario' that specifies which scenario
        # a given row belongs to
        self.dfs: Dict[str, pd.DataFrame] = {}

        # Check that the scenario names are unique
        all_names = list(map(lambda s: s.name, scenarios))
        if len(all_names) > len(
            set(all_names)
        ):  # set() drops duplicates, so if not unique len() will be less
            raise Exception("Scenario names are not unique.")

        # Disables warnings that will occur since we are constantly returning only a slice of our master dataframe
        pd.options.mode.chained_assignment = None

    def _load_dataframe(self, csv, folder):
        """Loads the dataframe into self.dfs[csv]"""
        df_all_scenarios: List[pd.DataFrame] = []
        for i, scenario in enumerate(self.scenarios):
            df = pd.read_csv(os.path.join(scenario.path, folder, csv + ".csv"))
            df["scenario_name"] = scenario.name
            df["scenario_index"] = i
            df_all_scenarios.append(df)

        self.dfs[csv] = pd.concat(df_all_scenarios)

    def get_dataframe(self, scenario_index, csv, folder=GraphDataFolder.OUTPUTS):
        """Return a dataframe filtered by the scenario_name"""
        if csv not in self.dfs:
            self._load_dataframe(csv, folder)

        df = self.dfs[csv]
        return df[df["scenario_index"] == scenario_index]

    def get_dataframe_all_scenarios(self, csv, folder=GraphDataFolder.OUTPUTS):
        """Fetch the dataframe containing all the scenarios"""
        if csv not in self.dfs:
            self._load_dataframe(csv, folder)

        return self.dfs[csv].copy()  # We return a copy so the source isn't modified


class GraphTools:
    """Object that is passed in graph( ). Provides utilities to make graphing easier"""

    def __init__(self, scenarios, graph_dir):
        """
        Create the GraphTools.

        @param scenarios list of scenarios that we should run graphing for
                graph_dir directory where graphs should be saved
        """
        self.scenarios: List[Scenario] = scenarios
        self.graph_dir = graph_dir

        # Number of graphs to display side by side
        self.num_scenarios = len(scenarios)
        # Create an instance of GraphData which stores the csv dataframes
        self.graph_data = GraphData(self.scenarios)
        # When True we are running compare(), when False we are running graph()
        # compare() is to create graphs for multiple scenarios
        # graph() is to create a graph just for the data of the active scenario
        self.is_compare_mode = False
        # When in graph mode, we move between scenarios. This index specifies the current scenario
        self.active_scenario = None
        # Maps a file name to a tuple where the tuple holds (fig, axs), the matplotlib figure and axes
        self.module_figures: Dict[str, Tuple] = {}

        # Provide link to useful libraries
        self.sns = sns
        self.pd = pd
        self.np = np

        # Provide useful mappings
        self.energy_source_map = {
            "Bio_Gas": "Biomass",
            "Bio_Liquid": "Biomass",
            "Bio_Solid": "Biomass",
            "DistillateFuelOil": "Oil",
            "ResidualFuelOil": "Oil",
            "Waste_Heat": "Waste Heat",
            "Electricity": "Battery Storage",
            "Water": "Hydro (pumped & not pumped)",
            "Uranium": "Nuclear",
        }

        self._energy_source_color_map = {
            # Color names use X11 colors
            "Oil": "black",
            "Biomass": "#008b45",
            "Coal": "#8b5a2b",
            "Gas": "#666666",
            "Geothermal": "red",
            "Solar": "gold",
            "Nuclear": "blueviolet",
            "Hydro (pumped & not pumped)": "#0066CC",
            "Wind": "deepskyblue",
            "Battery Storage": "aquamarine",
            "Waste Heat": "brown",
            "Other": "white",
        }

        # Set the style to Seaborn default style
        sns.set()

    def _create_axes(self, out, title=None, size=(8, 5)):
        """Create a set of axes"""
        num_subplot_columns = 1 if self.is_compare_mode else self.num_scenarios
        fig, ax = plt.subplots(nrows=1, ncols=num_subplot_columns, sharey="row")

        # If num_subplot_columns is 1, ax is not a list but we want it to be a list
        # so we replace ax with [ax]
        if num_subplot_columns == 1:
            ax = [ax]

        # Set a title to each subplot
        if num_subplot_columns > 1:
            for i, a in enumerate(ax):
                a.set_title(f"Scenario: {self.scenarios[i].name}")

        # Set a title for the figure
        if title is None:
            print(
                f"Warning: no title set for graph {out}.csv. Specify 'title=' in get_new_axes()"
            )
        else:
            fig.suptitle(title)

        # Set figure size based on numbers of subplots
        fig.set_size_inches(size[0] * num_subplot_columns, size[1])

        # Save the axes to module_figures
        self.module_figures[out] = (fig, ax)

    def get_energy_source_color_map(self, n) -> Dict[str, List[str]]:
        """
        Returns a colormap, which is a dictionary mapping a energy source to a list of elements of the same color

        @param n is the length of the list, normally the length of the series that the color map is used for
        """
        return {
            source: [color] * n
            for source, color in self._energy_source_color_map.items()
        }

    def get_new_axes(self, out, *args, **kwargs):
        """Returns a set of matplotlib axes that can be used to graph."""
        # If we're on the first scenario, we want to create the set of axes
        if self.is_compare_mode or self.active_scenario == 0:
            self._create_axes(out, *args, **kwargs)

        # Fetch the axes in the (fig, axs) tuple then select the axis for the active scenario
        return self.module_figures[out][1][
            0 if self.is_compare_mode else self.active_scenario
        ]

    def get_dataframe(self, *args, **kwargs):
        """Returns the dataframe for the active scenario"""
        if self.is_compare_mode:
            return self.graph_data.get_dataframe_all_scenarios(*args, **kwargs)
        else:
            return self.graph_data.get_dataframe(self.active_scenario, *args, **kwargs)

    def graph_module(self, func_graph):
        """Runs the graphing function for each comparison run"""
        self.is_compare_mode = False
        # For each scenario
        for i, scenario in enumerate(self.scenarios):
            # Set the active scenario index so that other functions behave properly
            self.active_scenario = i
            # Call the graphing function
            func_graph(self)
        self.active_scenario = None  # Reset to none to avoid accidentally selecting data when not graphing per scenario

        # Save the graphs
        self._save_plots()

    def compare_module(self, func_compare):
        self.is_compare_mode = True
        func_compare(self)
        self._save_plots()

    def _save_plots(self):
        for name, (fig, axs) in self.module_figures.items():
            fig.savefig(os.path.join(self.graph_dir, name), bbox_inches="tight")
        # Reset our module_figures dict
        self.module_figures = {}

    def get_active_scenario_path(self):
        return self.scenarios[self.active_scenario].path


def main():
    # Start a timer
    timer = StepTimer()

    # Read the cli arguments
    args = parse_args()

    # Load the SWITCH modules
    module_names = load_modules(args.scenarios)
    if len(module_names) == 0:
        # We'd raise an exception however warnings are already generated by load_modules
        print("No modules found.")
        return

    # Get the folder where we should save the graphs (also prompts that we want to overwrite
    graph_dir = get_graphing_folder(args)

    # Initialize the graphing tool
    graph_tools = GraphTools(scenarios=args.scenarios, graph_dir=graph_dir)

    # Loop through every graphing module
    print(f"Graphing modules:")
    for name, func_graph in iterate_modules(module_names, "graph"):
        # Graph
        print(f"{name}.graph()...")
        graph_tools.graph_module(func_graph)

    if len(args.scenarios) > 1:
        for name, func_compare in iterate_modules(module_names, "compare"):
            print(f"{name}.compare()...")
            graph_tools.compare_module(func_compare)

    print(f"Took {timer.step_time_as_str()} to generate all graphs.")


def iterate_modules(module_names, func_name):
    """This function is an Iterable that returns only modules with function graph()"""
    for name in module_names:
        module = sys.modules[name]
        # If the module has graph(), yield the module
        if hasattr(module, func_name):
            yield name, getattr(module, func_name)


def load_modules(compare_dirs):
    """Loads all the modules found in modules.txt"""

    def read_modules_txt(compare_dir):
        """Returns a sorted list of all the modules in a run folder (by reading modules.txt)"""
        with compare_dir:
            module_list = switch_model.solve.get_module_list(include_solve_module=False)
        return np.sort(module_list)

    print(f"Loading modules...")
    # Split compare_dirs into a base and a list of others
    compare_dir_base, compare_dir_others = compare_dirs[0], compare_dirs[1:]
    module_names = read_modules_txt(compare_dir_base)

    # Check that all the compare_dirs have equivalent modules.txt
    for compare_dir_other in compare_dir_others:
        if not np.array_equal(module_names, read_modules_txt(compare_dir_other)):
            print(
                f"WARNING: modules.txt is not equivalent between {compare_dir_base} and {compare_dir_other}."
                f"We will use the modules.txt in {compare_dir_base} however this may result in missing graphs and/or errors."
            )

    # Import the modules
    for module_name in module_names:
        importlib.import_module(module_name)

    return module_names


def parse_args():
    parser = argparse.ArgumentParser(
        description="Graph the outputs and inputs of SWITCH"
    )
    parser.add_argument(
        "--compare", nargs="+", default=["."], help="Specify a list of runs to compare"
    )
    parser.add_argument(
        "--graphs-dir",
        default="graphs",
        type=str,
        help="Name of the folder where the graphs should be saved",
    )
    parser.add_argument(
        "--overwrite",
        default=False,
        action="store_true",
        help="Don't prompt before overwriting the existing folder",
    )
    parser.add_argument(
        "--names", nargs="+", default=None, help="Names of the scenarios"
    )

    args = parser.parse_args()

    if len(args.compare) == 1:
        name = args.names[0] if args.names is not None else None
        args.scenarios = [Scenario(args.compare[0], name)]
    else:
        args.scenarios = []

        for i, rel_path in enumerate(args.compare):
            name = rel_path if args.names is None else args.names[i]
            args.scenarios.append(Scenario(rel_path, name=name))

    args.compare = None  # Erase args.compare to ensure we are accessing the args.scenarios, not args.compare
    return args


def get_graphing_folder(args):
    graphs_dir = args.graphs_dir

    # If we are comparing, then we want to force the user to pick a more descriptive name than "graphs
    if len(args.scenarios) > 1 and graphs_dir == "graphs":
        raise Exception(
            "Please specify a descriptive folder name for where the graphs should be saved using --graphs-dir."
        )

    # Remove the directory if it already exists
    if os.path.exists(graphs_dir):
        if not args.overwrite and not query_yes_no(
            f"Folder '{graphs_dir}' already exists. Are you sure you want to delete all its contents?"
        ):
            raise Exception("User aborted operation.")
    else:
        # Then recreate it so that its empty to the reader.
        os.mkdir(graphs_dir)

    return graphs_dir
