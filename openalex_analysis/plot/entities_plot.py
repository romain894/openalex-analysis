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
    """!
    EntitiesPlot class which contains generic methods to do plots of OpenAlex entities
    """
    
    def get_figure_entities_of_a_concept_color_country(self, concept, plot_parameters = None):
        """!
        @brief      Gets the figure with the entities of a concept, and with the country
                    as color
        
        @param      concept          The concept (str)
        @param      plot_parameters  The plot parameters (dict)
        
        @return     The figure (fig)
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
                                                concept,
                                                plot_parameters,
                                                x_threshold = 0,
                                                y_threshold = 0,
                                                cited_by_threshold = 0,
                                                display_only_selected_entities = None,
                                                display_threshold_lines = None,
                                                entity_to_highlight = None):
        """!
        @brief      Gets the figure with the entities of a concept and the selection threshold lines (optional)

        @param      concept                         The concept (str)
        @param      plot_parameters                 The plot parameters (dict)
        @param      x_threshold                     The x threshold (float or int)
        @param      y_threshold                     The y threshold (float or int)
        @param      cited_by_threshold              The cited by threshold (float or int)
        @param      display_only_selected_entities  The display only selected entities (bool)
        @param      display_threshold_lines         The display threshold lines (bool)
        @param      entity_to_highlight             The entity to highlight on the plot (str)

        @return     The figure (fig)
        """

        # extract the dictionnary plot_parameters:
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
                px.scatter(entities_df_filtered.loc[entities_df_filtered['id'] == entity_to_highlight], x=x_datas, y=y_datas, custom_data=self.getCustomData(concept)
                          ).update_traces(marker_size=20, marker={'size':20, 'symbol':'y-up', 'line':{'width':3, 'color':'black'}}).data
            )

        fig1.update_traces(hovertemplate="<br>".join(self.getHoverTemplate(concept)))

        # figure with containning all subfigures
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
                                                        element = None,
                                                        plot_title = None,
                                                        x_datas = 'year',
                                                        x_legend = "Year",
                                                        y_datas = None,
                                                        color_legend = "Entities"):
        """!
        @brief      Gets the figure with the time series usage of a element (eg
                    reference, concept) by entities
        
        @param      element       The element (default first in the dataframe) (str)
        @param      plot_title    The plot title (str)
        @param      x_datas       The x datas (default: year) (str)
        @param      x_legend      The x legend (str)
        @param      y_datas       The y datas (the entities to plot, the default
                                  is all entities in the dataframe) (list[str])
        @param      color_legend  The color legend (str)
        
        @return     The figure (fig)
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
    """!
    @brief      This class contains specific methods for Works concepts plot.
    """

    def getCustomData(self, concept):
        """!
        @brief      Gets the custom data for the plot

        @param      concept  The concept (str)

        @return     The custom data (list of str)
        """
        return ['display_name', 'country_name', 'institution_name', 'publication_year', 'cited_by_count', concept]


    def getHoverTemplate(self, concept):#, x_datas = None, x_legend = None, y_datas = None, y_legend = None, color_data = None, color_legend = None):
        """!
        @brief      Gets the hover template for the plot

        @param      concept  The concept (str)

        @return     The hover template (list of str)
        """
        hover_template = [
                "%{customdata[0]}",
                "Country name: %{customdata[1]}",
                "Institution: %{customdata[2]}",
                "Publication year: %{customdata[3]}",
                "Cited by count: %{customdata[4]}",
                "Concept score ("+self.concepts_names[concept]+"): %{customdata[5]}",
        ]
        # if x_datas != None and x_legend != None and x_datas not in self.getCustomData(concept):
        #     hover_template.append(x_legend+": %{x}")
        # if y_datas != None and y_legend != None and y_datas not in self.getCustomData(concept):
        #     hover_template.append(y_legend+": %{y}")
        # if color_data != None and color_legend != None and color_data not in self.getCustomData(concept):
        #     hover_template.append(color_legend+": %{marker.color}")
        return hover_template


    def get_figure_nb_time_referenced(self, element_type):
        """!
        @brief      Gets the figure with the number of time each reference is used in a
                    list of works.
        
        @param      element_type  The element type
        
        @return     The figure works number of time referenced (fig)
        """
        n_x = 2000 # x resolution of the plot
        references_works_count = self.get_element_count(element_type = element_type)
        x_references_works_count = np.geomspace(1, len(references_works_count), num=n_x, dtype=int)
        y_references_works_count = [references_works_count[x-1] for x in x_references_works_count]
        fig = px.line(x=x_references_works_count,
                      y=y_references_works_count,
                      log_x=True,
                      labels={'x':'Element rank', 'y':'Number of time used'},
                      title="Number of time the same element is used by the works in "+self.get_name_of_entitie(),
                      line_shape='hv')
        return fig


class AuthorsPlot(EntitiesPlot, AuthorsAnalysis):
    pass


class SourcesPlot(EntitiesPlot, SourcesAnalysis):
    pass


class InstitutionsPlot(EntitiesPlot, InstitutionsAnalysis):
    """!
    @brief      This class contains specific methods for Institutions concepts plot.
    """

    def getCustomData(self, concept):
        """!
        @brief      Gets the custom data for the plot

        @param      concept  The concept (str)

        @return     The custom data (list of str)
        """
        return ['display_name', 'geo.country', 'cited_by_count', 'works_cited_by_count_average', concept]


    def getHoverTemplate(self, concept):
        """!
        @brief      Gets the hover template for the plot

        @param      concept  The concept (str)

        @return     The hover template (list of str)
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


    def get_figure_institutions_multi_concepts_filtered(self, plot_parameters, concepts_from, concepts_filters, thresholds, x_threshold, cited_by_threshold, institution_to_highlight):
        """!
        @brief      Gets the figure with the institutions of multiple concepts and
                    filtered
        
        @param      plot_parameters           The plot parameters (dict)
        @param      concepts_from             The concepts to import to create
                                              the dataset (list of str)
        @param      concepts_filters          The concepts to use to filter the
                                              institutions (list of str)
        @param      thresholds                The thresholds for each concept
                                              filter (list of float or int)
        @param      x_threshold               The global threshold (eg nb of
                                              works), usually corresponding to
                                              the x data (float or int)
        @param      cited_by_threshold        The cited by threshold (float or
                                              int)
        @param      institution_to_highlight  The institution to highlight on
                                              the plot (str)
        
        @return     The figure (fig)
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
        self.add_average_combined_concept_score_to_multi_concept_entitie_df(concepts_from)

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

        # figure with containning all subfigures
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
    pass


class PublishersPlot(EntitiesPlot, PublishersAnalysis):
    pass