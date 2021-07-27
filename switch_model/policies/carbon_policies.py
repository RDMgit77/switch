# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
"""
Add emission policies to the model, either in the form of an added cost, or of
an emissions cap, depending on data inputs. The added cost could represent the
social cost of carbon, the expected clearing price of a cap-and-trade carbon
market, or a carbon tax.

Specifying carbon_cap_tco2_per_yr will add a system-wide emissions cap:
    AnnualEmissions[period] <= carbon_cap_tco2_per_yr[period]
Note: carbon_cap_tco2_per_yr defaults to infinity (no cap) for any data that
is unspecified.

Specifying carbon_cost_dollar_per_tco2 will add a term to the objective function:
    AnnualEmissions[period] * carbon_cost_dollar_per_tco2[period]
Note: carbon_cost_dollar_per_tco2 defaults to 0 (no cost) for any data that
is unspecified.

Specifying any of   carbon_cap_tnox_per_yr, carbon_cost_dollar_per_tnox,
                    carbon_cap_tso2_per_yr, carbon_cost_dollar_per_tso2,
                    carbon_cap_tch4_per_yr, carbon_cost_dollar_per_tch4
    will have the same effect as descibed above, just for different greenhouse gases.

"""
from __future__ import division
import os
from pyomo.environ import Set, Param, Expression, Constraint, Suffix
import switch_model.reporting as reporting
from switch_model.tools.graph import graph
from switch_model.utilities import results_info


def define_components(model):
    model.carbon_cap_tco2_per_yr = Param(model.PERIODS, default=float('inf'), doc=(
        "CO2 emissions from this model must be less than this cap. This is specified in metric tonnes of CO2 per year."))
    model.carbon_cap_tnox_per_yr = Param(model.PERIODS, default=float('inf'), doc=(
        "NOx emissions from this model must be less than this cap. This is specified in metric tonnes of NOx per year."))
    model.carbon_cap_tso2_per_yr = Param(model.PERIODS, default=float('inf'), doc=(
        "SO2 emissions from this model must be less than this cap. This is specified in metric tonnes of SO2 per year."))
    model.carbon_cap_tch4_per_yr = Param(model.PERIODS, default=float('inf'), doc=(
        "CH4 emissions from this model must be less than this cap. This is specified in metric tonnes of CH4 per year."))

    # We use a scaling factor to improve the numerical properties
    # of the model. The scaling factor was determined using trial
    # and error and this tool https://github.com/staadecker/lp-analyzer.
    # Learn more by reading the documentation on Numerical Issues.
    enforce_carbon_cap_scaling_factor = 1e-1
    model.Enforce_Carbon_Cap = Constraint(model.PERIODS,
        rule=lambda m, p:
            Constraint.Skip if m.carbon_cap_tco2_per_yr[p] == float('inf')
            else m.AnnualEmissions[p] * enforce_carbon_cap_scaling_factor <= m.carbon_cap_tco2_per_yr[p]
                                          * enforce_carbon_cap_scaling_factor,
            doc=("Enforces the carbon cap for generation-related CO2 emissions."))

    model.Enforce_Carbon_Cap_NOx = Constraint(
        model.PERIODS,
        rule=lambda m, p:
              Constraint.Skip if m.carbon_cap_tnox_per_yr[p] == float('inf')
              else m.AnnualEmissionsNOx[p] <= m.carbon_cap_tnox_per_yr[p],
        doc="Enforces the carbon cap for generation-related NOx emissions.")

    model.Enforce_Carbon_Cap_SO2 = Constraint(
        model.PERIODS,
        rule=lambda m, p:
              Constraint.Skip if m.carbon_cap_tso2_per_yr[p] == float('inf')
              else m.AnnualEmissionsSO2[p] <= m.carbon_cap_tso2_per_yr[p],
        doc="Enforces the carbon cap for generation-related SO2 emissions.")

    model.Enforce_Carbon_Cap_CH4 = Constraint(
        model.PERIODS,
        rule=lambda m, p:
              Constraint.Skip if m.carbon_cap_tch4_per_yr[p] == float('inf')
              else m.AnnualEmissionsCH4[p] <= m.carbon_cap_tch4_per_yr[p],
        doc="Enforces the carbon cap for generation-related CH4 emissions.")

    # Make sure the model has a dual suffix for determining implicit carbon costs
    model.enable_duals()

    model.carbon_cost_dollar_per_tco2 = Param(
        model.PERIODS, default=0.0,
        doc="The cost adder applied to CO2 emissions, in future dollars per metric tonne of CO2.")
    model.carbon_cost_dollar_per_tnox = Param(
        model.PERIODS, default=0.0,
        doc="The cost adder applied to NOx emissions, in future dollars per metric tonne of NOx.")
    model.carbon_cost_dollar_per_tso2 = Param(
        model.PERIODS, default=0.0,
        doc="The cost adder applied to SO2 emissions, in future dollars per metric tonne of SO2.")
    model.carbon_cost_dollar_per_tch4 = Param(
        model.PERIODS, default=0.0,
        doc="The cost adder applied to CH4 emissions, in future dollars per metric tonne of CH4.")

    model.EmissionsCosts = Expression(
        model.PERIODS,
        rule=(lambda m, p:
              m.AnnualEmissions[p] * m.carbon_cost_dollar_per_tco2[p] +
              m.AnnualEmissionsNOx[p] * m.carbon_cost_dollar_per_tnox[p] +
              m.AnnualEmissionsSO2[p] * m.carbon_cost_dollar_per_tso2[p] +
              m.AnnualEmissionsCH4[p] * m.carbon_cost_dollar_per_tch4[p]),
        doc="Enforces the carbon cap for generation-related emissions.")

    model.Cost_Components_Per_Period.append('EmissionsCosts')


def load_inputs(model, switch_data, inputs_dir):
    """
    Typically, people will specify either carbon caps or carbon costs, but not
    both. If you provide data for both columns, the results may be difficult
    to interpret meaningfully.

    Expected input files:
    carbon_policies.csv
        PERIOD, carbon_cap_tco2_per_yr, carbon_cost_dollar_per_tco2,
        carbon_cap_tnox_per_yr, carbon_cost_dollar_per_tnox,
        carbon_cap_tso2_per_yr, carbon_cost_dollar_per_tso2,
        carbon_cap_tch4_per_yr, carbon_cost_dollar_per_tch4,

    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'carbon_policies.csv'),
        optional=True,
        optional_params=(model.carbon_cap_tco2_per_yr, model.carbon_cost_dollar_per_tco2,
                         model.carbon_cap_tnox_per_yr, model.carbon_cost_dollar_per_tnox,
                         model.carbon_cap_tso2_per_yr, model.carbon_cost_dollar_per_tso2,
                         model.carbon_cap_tch4_per_yr, model.carbon_cost_dollar_per_tch4),
        auto_select=True,
        param=(model.carbon_cap_tco2_per_yr, model.carbon_cost_dollar_per_tco2,
               model.carbon_cap_tnox_per_yr, model.carbon_cost_dollar_per_tnox,
               model.carbon_cap_tso2_per_yr, model.carbon_cost_dollar_per_tso2,
               model.carbon_cap_tch4_per_yr, model.carbon_cost_dollar_per_tch4))


def post_solve(model, outdir):
    """
    Export annual emissions, carbon cap, and implicit carbon costs (where
    appropriate). The dual values of the carbon cap constraint represent an
    implicit carbon cost for purely linear optimization problems. For mixed
    integer optimization problems, the dual values lose practical
    interpretations, so dual values are only exported for purely linear
    models. If you include minimum build requirements, discrete unit sizes,
    discrete unit commitment, or other integer decision variables, the dual
    values will not be exported.
    """
    def get_row(model, period):
        # Loop through all 4 green house gases (GHG) and add the value to the row.
        GHGs = [
            {"AnnualEmissions": model.AnnualEmissions, "cap": model.carbon_cap_tco2_per_yr,
             "cost_per_t": model.carbon_cost_dollar_per_tco2, "Enforce_Carbon_Cap": "Enforce_Carbon_Cap"},
            {"AnnualEmissions": model.AnnualEmissionsNOx, "cap": model.carbon_cap_tnox_per_yr,
             "cost_per_t": model.carbon_cost_dollar_per_tnox, "Enforce_Carbon_Cap": "Enforce_Carbon_Cap_NOx"},
            {"AnnualEmissions": model.AnnualEmissionsSO2, "cap": model.carbon_cap_tso2_per_yr,
             "cost_per_t": model.carbon_cost_dollar_per_tso2, "Enforce_Carbon_Cap": "Enforce_Carbon_Cap_SO2"},
            {"AnnualEmissions": model.AnnualEmissionsCH4, "cap": model.carbon_cap_tch4_per_yr,
             "cost_per_t": model.carbon_cost_dollar_per_tch4, "Enforce_Carbon_Cap": "Enforce_Carbon_Cap_CH4"},
        ]

        return (period,) + tuple(
            c
            for GHG in GHGs
            for c in
            (
                GHG["AnnualEmissions"][period],
                GHG["cap"][period],
                model.get_dual(
                    GHG["Enforce_Carbon_Cap"],
                    period,
                    divider=model.bring_annual_costs_to_base_year[period]
                ),
                GHG["cost_per_t"][period],
                GHG["cost_per_t"][period] * GHG["AnnualEmissions"][period]
            )
        )

    reporting.write_table(
        model, model.PERIODS,
        output_file=os.path.join(outdir, "emissions.csv"),
        headings=("PERIOD",
                  "AnnualEmissions_tCO2_per_yr", "carbon_cap_tco2_per_yr", "carbon_cap_dual_future_dollar_per_tco2",
                  "carbon_cost_dollar_per_tco2", "carbon_cost_annual_total_co2",
                  "AnnualEmissions_tNOx_per_yr", "carbon_cap_tNOx_per_yr", "carbon_cap_dual_future_dollar_per_tnox",
                  "carbon_cost_dollar_per_tnox", "carbon_cost_annual_total_nox",
                  "AnnualEmissions_tSO2_per_yr", "carbon_cap_tso2_per_yr", "carbon_cap_dual_future_dollar_per_tso2",
                  "carbon_cost_dollar_per_tso2", "carbon_cost_annual_total_so2",
                  "AnnualEmissions_tCH4_per_yr", "carbon_cap_tch4_per_yr", "carbon_cap_dual_future_dollar_per_tch4",
                  "carbon_cost_dollar_per_tch4", "carbon_cost_annual_total_ch4",
                  ),
        values=get_row)


@graph(
    "emissions",
    "Emissions per period"
)
def graph_emissions(tools):
    df = tools.get_dataframe("emissions.csv", convert_dot_to_na=True)
    # Plot emissions over time
    df['AnnualEmissions_tCO2_per_yr'] *= 1e-6  # Convert to MMtCO2
    if df["AnnualEmissions_tCO2_per_yr"].sum() == 0:
        results_info.add_info("CO2 Emissions", "No Emissions")
        return
    tools.sns.barplot(
        x='PERIOD',
        y='AnnualEmissions_tCO2_per_yr',
        data=df,
        ax=tools.get_axes(ylabel='CO2 Emissions (MMtCO2/yr)'),
        color='gray'
    )

@graph(
    "emissions_duals",
    "Carbon cap dual values per period"
)
def graph_emissions_duals(tools):
    df = tools.get_dataframe("emissions.csv", convert_dot_to_na=True)
    # Keep only the duals for every period
    df = df.set_index("PERIOD")["carbon_cap_dual_future_dollar_per_tco2"]
    df = df.dropna()
    if df.empty:
        return
    df *= -1  # Flip to positive values since duals are negative by default
    df.plot(
        kind="bar",
        ax=tools.get_axes(ylabel='Dual values ($/tCO2)'),
        color='gray'
    )
