# Romain THOMAS 2023
# Stockholm Resilience Centre, Stockholm University

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# config must NOT be imported from pyalex here as it is already imported via entities_analysis

from openalex_analysis.analysis import *


figure_height = 800


class EntitiesPlot():
    """
    EntitiesPlot class which contains generic methods to do plots of OpenAlex entities.
    """

    def get_figure_entities_of_a_concept_color_country(self,
                                                       concept: str,
                                                       plot_parameters: dict | None = None
                                                       ) -> go.Figure:
        """
        Gets the figure with the entities of a concept, and with the country as color.

        :param concept: The concept id.
        :type concept: str
        :param plot_parameters: The plot parameters.
        :type plot_parameters: dict | None
        :return: The figure.
        :rtype: go.Figure
        """
        if plot_parameters == None:
            plot_parameters = {
                'plot_title': "Plot of the entities related to "+self.concepts_names[concept]+" studies",
                'x_datas': 'works_count',
                'x_legend': "Number of works",
                'y_datas': concept,
                'y_legend': "Concept score ("+self.concepts_names[concept]+")",
            }
        plot_title = plot_parameters['plot_title']
        x_datas = plot_parameters['x_datas']
        x_legend = plot_parameters['x_legend']
        y_datas = plot_parameters['y_datas']
        y_legend = plot_parameters['y_legend']
        color_data = self.getCustomData(concept)[1]
        color_legend = 'Country name'
        # self.create_institutions_dataframe(concept)
        # self.create_entities_dataframe(concept)

        fig = px.scatter(self.entities_df,
                         x=x_datas,
                         y=y_datas,
                         log_x=True,
                         custom_data=self.getCustomData(concept),
                         color=color_data,
                         # sort the elements and push the None elements at the end
                         category_orders={color_data: sorted(self.entities_df[color_data], key=lambda x: (x is None, x))},
                         labels={x_datas:x_legend, y_datas:y_legend, color_data:color_legend},
                         height=800)

        fig.update_traces(hovertemplate="<br>".join(self.getHoverTemplate(concept)))

        fig.update_yaxes(type='linear')

        fig.update_layout(
            title={
                'text': plot_title,
                'x':0.5,
                'xanchor': 'center',
                'yanchor': 'top'
            },
        )

        return fig

    # TODO: redo filters
    # TODO: keep for work? useless for now because color_data = x_datas + bug in numpy:
    # fix or remove casting='unsafe', which apparently create problem with conversion
    # (only two colors for the works on the plot) SOLVED?
    def get_figure_entities_selection_threshold(self,
                                                concept: str,
                                                plot_parameters: dict,
                                                x_threshold: float | int = 0,
                                                y_threshold: float | int = 0,
                                                cited_by_threshold: float | int = 0,
                                                display_only_selected_entities: list | None = None,
                                                display_threshold_lines: list | None = None,
                                                entity_to_highlight: str | None = None
                                                ) -> go.Figure:
        """
        Get the figure with the entities of a concept and the selection threshold lines (optional).

        :param concept: The concept id.
        :type concept: str
        :param plot_parameters: The plot parameters.
        :type plot_parameters:  dict
        :param x_threshold: The x threshold.
        :type x_threshold: float | int
        :param y_threshold: The y threshold.
        :type y_threshold: float | int
        :param cited_by_threshold: The cited by threshold.
        :type cited_by_threshold: float | int
        :param display_only_selected_entities: The display only selected entities. TODO: change type
        :type display_only_selected_entities: list | None
        :param display_threshold_lines: The display threshold lines. TODO: change type
        :type display_threshold_lines: list | None
        :param entity_to_highlight: The entity to highlight on the plot.
        :type entity_to_highlight: str | None
        :return: The figure.
        :rtype: go.Figure
        """
        # extract the dictionary plot_parameters:
        plot_title = plot_parameters['plot_title']
        x_datas = plot_parameters['x_datas']
        x_legend = plot_parameters['x_legend']
        y_datas = plot_parameters['y_datas']
        y_legend = plot_parameters['y_legend']
        color_data = plot_parameters['color_data']
        color_legend = plot_parameters['color_legend']

        df_filters = {}
        if cited_by_threshold > 0:
            df_filters['works_cited_by_count_average'] = cited_by_threshold
        if display_only_selected_entities != None and len(display_only_selected_entities):
            df_filters[x_datas] = x_threshold
            df_filters[y_datas] = y_threshold

        entities_df_filtered = self.get_df_filtered_entities_selection_threshold(df_filters)

        # convert the input list from the GUI to a boolean
        if display_threshold_lines != None:
            if len(display_threshold_lines):
                display_threshold_lines = True
            else:
                display_threshold_lines = False

        # create the figure with the scatter plot of entities        
        fig1 = px.scatter(entities_df_filtered,
                         x=x_datas,
                         y=y_datas,
                         #custom_data=np.stack((entities_df_filtered['display_name'], entities_df_filtered['type'])),
                         custom_data=self.getCustomData(concept),
                         # log10 scale for the color and fill 0 when value = 0 (can't compute log(0))
                         color=np.log10(entities_df_filtered[color_data].to_numpy(dtype=float), where=entities_df_filtered[color_data]!=0, out=np.zeros_like(entities_df_filtered[color_data], dtype=float)),
                         #color=np.log10(entities_df_filtered[color_data].values, where=entities_df_filtered[color_data]!=0, out=np.zeros_like(entities_df_filtered[color_data]),  casting='unsafe'),
                         #color=entities_df_filtered[color_data],
                         labels={x_datas:x_legend, y_datas:y_legend})

        # Entity to highlight on the plot:
        if entity_to_highlight != None:
            fig1.add_traces(
                px.scatter(entities_df_filtered.loc[entities_df_filtered['id'] == entity_to_highlight],
                           x=x_datas,
                           y=y_datas,
                           custom_data=self.getCustomData(concept)
                          ).update_traces(marker_size=20,
                                          marker={'size':20, 'symbol':'y-up', 'line':{'width':3, 'color':'black'}}
                                          ).data
            )

        fig1.update_traces(hovertemplate="<br>".join(self.getHoverTemplate(concept)))

        # figure with containing all sub figures
        fig0 = None

        if display_threshold_lines:
            # create the figures with the threshold lines
            if len(entities_df_filtered.index) > 0:
                x_min = int(np.amin(entities_df_filtered[x_datas]))
                x_max = int(np.amax(entities_df_filtered[x_datas]))
                y_min = int(np.amin(entities_df_filtered[y_datas]))
                y_max = int(np.amax(entities_df_filtered[y_datas]))
            else:
                # the dataframe is empty
                x_min = 0
                x_max = 1
                y_min = 0
                y_max = 1
            fig2 = px.line(x=[x_threshold, x_threshold], y=[min(y_min, y_threshold), y_max])
            fig3 = px.line(x=[min(x_min, x_threshold), x_max], y=[y_threshold, y_threshold])

            # create the main figure
            fig0 = go.Figure(data=fig1.data + fig2.data + fig3.data,
                             layout={'height':figure_height})
        else:
            # create the main figure
            fig0 = go.Figure(data=fig1.data,
                             layout={'height':figure_height})

        fig0.update_xaxes(type="log")

        # change the tick values in the legend as the value used to plot is log10(val)
        #color_vals = np.linspace(0, int(np.amax(np.log10(entities_df_filtered['cited_by_count']))), num=7)
        color_vals = [-2, -1, 0, 1, 2, 3, 4]
        #color_names = color_vals ** 10 #np.logspace(0, int(np.amax(entities_df_filtered['cited_by_count'])), num=7)
        color_names = ['0.01', '0.1', '1', '10', '100', '1k', '10k']

        fig0.update_layout(
            coloraxis_colorbar=dict(
                title=color_legend,
                tickmode='array',
                tickvals=color_vals,
                ticktext=color_names
            ),
            coloraxis = {'colorscale':'rainbow'},
            title={
                'text': plot_title,
                'x':0.5,
                'xanchor': 'center',
                'yanchor': 'top'
            },
            xaxis_title=x_legend,
            yaxis_title=y_legend
        )

        return fig0


    def get_figure_time_series_element_used_by_entities(self,
                                                        element: str | None = None,
                                                        plot_title: str | None = None,
                                                        x_datas: str = 'year',
                                                        x_legend: str = "Year",
                                                        y_datas: list[str] | None = None,
                                                        color_legend: str = "Entities"
                                                        ) -> go.Figure:
        """
        Get the figure with the time series usage of a element (eg. reference, concept) by entities.

        :param element: The element id. The default value is None. When the element is None, the first element id in the element_count_df is selected.
        :type element: str | None
        :param plot_title: The plot title. The default value is None to generate an appropriate title.
        :type plot_title: str | None
        :param x_datas: The x datas. The default value is 'year'.
        :type x_datas: str
        :param x_legend: The x legend. The default value is "Year".
        :type x_legend: str
        :param y_datas: The y datas (the entities to plot). The default value is None to use all the entities in the dataframe.
        :type y_datas: list[str] | None
        :param color_legend: The color legend. TODO: delete because unused?
        :type color_legend: str
        :return: The figure.
        :rtype: go.Figure
        """
        df = self.element_count_df

        if element == None:
            # take the first element to plot
            element = df.index[0][0]
        element_id = element.strip("https://openalex.org/")
        # if y_legend == None:
        #     y_legend = self.get_name_of_entitie(element.strip("https://openalex.org/"))
        if plot_title == None:
            element_name = self.get_name_of_entitie(element_id)
            if len(element_name) > 70:
                element_name = element_name[0:70]+"..."
            plot_title = "Plot of the yearly usage of "+element_id+" ("+element_name+") by the entities"
        if y_datas == None:
            y_datas = self.count_entities_cols

        df = df[y_datas].loc[element].reset_index()

        df = pd.melt(df, id_vars=x_datas, value_vars=df.columns[1:], var_name='entitie', value_name='nb_used')

        fig = px.line(df,
                      x=x_datas,
                      y='nb_used',
                      color='entitie',
                      labels={x_datas:x_legend})

        fig.update_layout(
            title={
                'text': plot_title,
                'x':0.5,
                'xanchor': 'center',
                'yanchor': 'top'
            },
        )

        return fig


class WorksPlot(EntitiesPlot, WorksAnalysis):
    """
    This class contains specific methods for Works plot.
    """

    def getCustomData(self, concept: str) -> list[str]:
        """
        Get the custom data for the plot.

        :param concept: The concept id.
        :type concept: str
        :return: The list of custom data for Works.
        :rtype: list[str]
        """
        return ['display_name', 'country_name', 'institution_name', 'publication_year', 'cited_by_count', concept]


    def getHoverTemplate(self, concept: str) -> list[str]:
        """
        Get the hover template for the plot.

        :param concept: The concept id.
        :type concept: str
        :return: The hover template.
        :rtype: list[str]
        """
        hover_template = [
                "%{customdata[0]}",
                "Country name: %{customdata[1]}",
                "Institution: %{customdata[2]}",
                "Publication year: %{customdata[3]}",
                "Cited by count: %{customdata[4]}",
                "Concept score ("+self.concepts_names[concept]+"): %{customdata[5]}",
        ]
        return hover_template


    def get_figure_nb_time_referenced(self, element_type: str) -> go.Figure:
        """
        Gets the figure with the number of time each reference is used in a list of works. Also work with concepts.
        TODO: change function name to be more inclusive?

        :param element_type: The element type ('reference' or 'concept').
        :type element_type: str
        :return: The figure.
        :rtype: go.Figure
        """
        n_x = 2000 # x resolution of the plot
        references_works_count = self.get_element_count(element_type = element_type)
        x_references_works_count = np.geomspace(1, len(references_works_count), num=n_x, dtype=int)
        y_references_works_count = [references_works_count[x-1] for x in x_references_works_count]
        fig = px.line(x=x_references_works_count,
                      y=y_references_works_count,
                      log_x=True,
                      labels={'x':'Element rank', 'y':'Number of time used'},
                      title="Number of time the same element is used by the works in "+self.get_name_of_entity(),
                      line_shape='hv')
        return fig


    def get_figure_entities_yearly_usage(self,
                                         count_years: list[int],
                                         entity_used_ids: str | list[str],
                                         entity_from_ids: str | list[str] | None = None,
                                        ) -> go.Figure:
        """
        Get the plot bar figure with the yearly usage of an entity (concept, work) in the works from another entity
        (institution, author).

        :param count_years: The years to count.
        :type count_years: list[int]
        :param entity_used_ids: The entities used.
        :type entity_used_ids: str | list[str]
        :param entity_from_ids: The entities which used the entities to count. The default value is None. If None, the entitie_from_id is used.
        :type entity_from_ids: str | list[str] | None
        :return: THe figure.
        :rtype: go.Figure
        """
        df = self.get_df_yearly_usage_of_entities_by_multiples_entities(
                                                                        count_years = count_years,
                                                                        entity_used_ids = entity_used_ids,
                                                                        entity_from_ids = entity_from_ids,
                                                                       )
        fig = px.bar(df,
                      x='years',
                      y='usage_count',
                      color='entity_from',
                      pattern_shape='entity_used',
                      barmode='group',
                      height=600,
                     )
        return fig


    def get_figure_entities_yearly_position(self,
                                            count_years: list[int],
                                            entity_used_ids: str,
                                            entity_from_ids: str | list[str] | None = None,
                                           ) -> go.Figure:
        """
        Get the plot figure with the yearly usage of an entity (concept, work) in the works from another entity
        (institution, author).

        :param count_years: The years to count.
        :type count_years: list[int]
        :param entity_used_ids: The entity used.
        :type entity_used_ids: str
        :param entity_from_ids: The entities which used the entities to count. The default value is None. If None, the entitie_from_id is used.
        :type entity_from_ids: str | list[str] | None
        :return: The figure.
        :rtype: go.Figure
        """
        df = self.get_df_yearly_usage_of_entities_by_multiples_entities(
                                                                        count_years = count_years,
                                                                        entity_used_ids = entity_used_ids,
                                                                        entity_from_ids = entity_from_ids,
                                                                       )
        fig = px.line(df,
                      x='works_count',
                      y='usage_count',
                      text='years',
                      color='entity_from',
                      line_dash='entity_used',
                      height=600,
                     )
        fig.update_traces(textposition="bottom right")
        return fig


class AuthorsPlot(EntitiesPlot, AuthorsAnalysis):
    """
    This class contains specific methods for Authors plot. Not used for now.
    """
    pass


class SourcesPlot(EntitiesPlot, SourcesAnalysis):
    """
    This class contains specific methods for Sources plot. Not used for now.
    """
    pass


class InstitutionsPlot(EntitiesPlot, InstitutionsAnalysis):
    """
    This class contains specific methods for Institutions plot.
    """

    def getCustomData(self, concept: str) -> list[str]:
        """
        Get the custom data for the plot.

        :param concept: The concept id.
        :type concept: str
        :return: The list of custom data for Institutions.
        :rtype: list[str]
        """
        return ['display_name', 'geo.country', 'cited_by_count', 'works_cited_by_count_average', concept]


    def getHoverTemplate(self, concept: str) -> list[str]:
        """
        Get the hover template for the plot.

        :param concept: The concept id.
        :type concept: str
        :return: The hover template.
        :rtype: list[str]
        """
        hover_template = [
            "%{customdata[0]}",
            "Country name: %{customdata[1]}",
            #y_legend+": %{y}",
            "Concept score ("+self.concepts_names[concept]+"): %{customdata[4]}",
            "Cited by count: %{customdata[2]}",
            "Cited by average: %{customdata[3]}"
        ]
        return hover_template


    def get_figure_institutions_multi_concepts_filtered(self,
                                                        plot_parameters: dict,
                                                        concepts_from: list[str],
                                                        concepts_filters: list[str],
                                                        thresholds: list[int | float],
                                                        x_threshold: int | float,
                                                        cited_by_threshold: float | int,
                                                        institution_to_highlight: str
                                                        ) -> go.Figure:
        """
        Gets the figure with the institutions of multiple concepts and filtered.

        :param plot_parameters: The plot parameters.
        :type plot_parameters: dict
        :param concepts_from: The concepts to import to create the dataset.
        :type concepts_from: list[str]
        :param concepts_filters: The concepts to use to filter the institutions.
        :type concepts_filters: list[str]
        :param thresholds: The thresholds for each concept filter.
        :type thresholds: list[int | float]
        :param x_threshold: The global threshold (eg. nb of works), usually corresponding to the x data (float or int).
        :type x_threshold: int | float
        :param cited_by_threshold: The cited by threshold (float or int).
        :type cited_by_threshold: int | float
        :param institution_to_highlight: The institution to highlight on the plot (str).
        :type institution_to_highlight: str
        :return: The figure.
        :rtype: go.Figure
        """
        # extract the dictionnary plot_parameters:
        plot_title = plot_parameters['plot_title']
        x_datas = plot_parameters['x_datas']
        x_legend = plot_parameters['x_legend']
        y_datas = plot_parameters['y_datas']
        y_legend = plot_parameters['y_legend']
        color_data = plot_parameters['color_data']
        color_legend = plot_parameters['color_legend']


        self.create_multi_concept_filters_entities_dataframe(concepts_from, concepts_filters, thresholds, x_datas, x_threshold, cited_by_threshold)
        self.add_average_combined_concept_score_to_multi_concept_entity_df(concepts_from)

        # create the figure with the scatter plot of institutions        
        fig1 = px.scatter(self.entities_multi_filtered_df,
                         x=x_datas,
                         y=y_datas,
                         #custom_data=np.stack((entities_df_filtered['display_name'], entities_df_filtered['type'])),
                         # change color_data by 'country_name' or update the hover if color_data changes
                         custom_data=['display_name', color_data, 'cited_by_count', 'works_cited_by_count_average'],
                         color=color_data,
                         category_orders={color_data: np.sort(self.entities_multi_filtered_df[color_data].unique()[self.entities_multi_filtered_df[color_data].unique() != None])},
                         labels={x_datas:x_legend, y_datas:y_legend})


        # Highlight SRC institution on the plot:
        fig1.add_traces(
            px.scatter(self.entities_multi_filtered_df.loc[self.entities_multi_filtered_df['id'] == institution_to_highlight], x=x_datas, y=y_datas, custom_data=['display_name', color_data, 'cited_by_count', 'works_cited_by_count_average']
                      ).update_traces(marker_size=20, marker={'size':20, 'symbol':'y-up', 'line':{'width':3, 'color':'black'}}).data
        )

        fig1.update_traces(hovertemplate="<br>".join([
                "%{customdata[0]}",
                #color_legend+": %{customdata[1]}",# already displayed on the plot
                x_legend+": %{x}",
                y_legend+": %{y}",
                "Cited by count: %{customdata[2]}",
                "Cited by average: %{customdata[3]}",
        ]))

        # figure with containing all sub figures
        fig0 = None

        # create the main figure
        fig0 = go.Figure(data=fig1.data,
                         layout={'height':figure_height})


        fig0.update_xaxes(type="log")

        fig0.update_layout(
            coloraxis = {'colorscale':'rainbow'},
            title={
                'text': plot_title,
                'x':0.5,
                'xanchor': 'center',
                'yanchor': 'top'
            },
            xaxis_title=x_legend,
            yaxis_title=y_legend
        )

        return fig0


class ConceptsPlot(EntitiesPlot, ConceptsAnalysis):
    """
    This class contains specific methods for Concepts plot. Not used for now.
    """
    pass


class PublishersPlot(EntitiesPlot, PublishersAnalysis):
    """
    This class contains specific methods for Publishers plot. Not used for now.
    """
    pass