# Romain THOMAS 2024

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from pyalex import Concepts, Institutions

# config must NOT be imported from pyalex here as it is already imported via entities_analysis

from openalex_analysis.analysis import *

figure_height = 800


class EntitiesPlot:
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
        if plot_parameters is None:
            plot_parameters = {
                'plot_title': "Plot of the entities related to " + Concepts()[concept]['display_name'] + " studies",
                'x_datas': 'works_count',
                'x_legend': "Number of works",
                'y_datas': concept,
                'y_legend': "Concept score (" + Concepts()[concept]['display_name'] + ")",
            }
        plot_title = plot_parameters['plot_title']
        x_datas = plot_parameters['x_datas']
        x_legend = plot_parameters['x_legend']
        y_datas = plot_parameters['y_datas']
        y_legend = plot_parameters['y_legend']
        color_data = self.getCustomData(concept)[1]
        color_legend = 'Country name'

        fig = px.scatter(
            self.entities_df,
            x=x_datas,
            y=y_datas,
            log_x=True,
            custom_data=self.getCustomData(concept),
            color=color_data,
            # sort the elements and push the None elements at the end
            category_orders={color_data: sorted(self.entities_df[color_data], key=lambda x: (x is None, x))},
            labels={x_datas: x_legend, y_datas: y_legend, color_data: color_legend},
            height=figure_height
        )

        fig.update_traces(hovertemplate="<br>".join(self.getHoverTemplate(concept)))

        fig.update_yaxes(type='linear')

        fig.update_layout(
            title={
                'text': plot_title,
                'x': 0.5,
                'xanchor': 'center',
                'yanchor': 'top'
            },
        )

        return fig


    def get_figure_time_series_element_used_by_entities(self,
                                                        element: str | None = None,
                                                        plot_title: str | None = None,
                                                        x_datas: str = 'year',
                                                        x_legend: str = "Year",
                                                        y_datas: list[str] | None = None,
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
        :return: The figure.
        :rtype: go.Figure
        """
        df = self.element_count_df

        if element is None:
            # take the first element to plot
            element = df.index[0][0]
        element_id = element.strip("https://openalex.org/")
        # if y_legend == None:
        #     y_legend = self.get_name_of_entitie(element.strip("https://openalex.org/"))
        if plot_title is None:
            element_name = self.get_name_of_entity(element_id)
            if len(element_name) > 70:
                element_name = element_name[0:70] + "..."
            plot_title = "Plot of the yearly usage of " + element_id + " (" + element_name + ") by the entities"
        if y_datas is None:
            y_datas = self.count_entities_cols

        df = df[y_datas].loc[element].reset_index()

        df = pd.melt(df, id_vars=x_datas, value_vars=df.columns[1:], var_name='entitie', value_name='nb_used')

        fig = px.line(
            df,
            x=x_datas,
            y='nb_used',
            color='entitie',
            labels={x_datas: x_legend}
        )

        fig.update_layout(
            title={
                'text': plot_title,
                'x': 0.5,
                'xanchor': 'center',
                'yanchor': 'top'
            },
        )

        return fig


    def get_figure_collaborations_with_institutions(self,
                                                    plot_title: str | None = None,
                                                    markers_size_scale: float = 0.3
                                                    ) -> go.Figure:
        """
        Get the figure with the collaborations with institutions.

        :param plot_title: The plot title. The default value is None to generate an appropriate title.
        :type plot_title: str | None
        :param markers_size_scale: The size scale of the markers. The default value is 0.3.
        :type markers_size_scale: float
        :return: The figure
        :rtype: go.Figure
        """
        self.collaborations_with_institutions_df['marker_size'] = (self.collaborations_with_institutions_df['count'] *
                                                                   markers_size_scale)
        if plot_title is None:
            plot_title = "Collaborations through journal articles"
            if self.collaborations_with_institutions_year is not None:
                plot_title += " in "+str(self.collaborations_with_institutions_year)
            plot_title += (
                '<br><sup>Data from OpenAlex. Made with Openalex Analysis'
                '(<a href="https://github.com/romain894/openalex-analysis">'
                'https://github.com/romain894/openalex-analysis</a>)</sup>'
            )
        fig = px.scatter_geo(
            self.collaborations_with_institutions_df,
                lat='lat',
                lon='lon',
                size='count',
                custom_data=['name', 'country', 'count', 'link_to_works'],
                width=1600, height=figure_height,
                color='name_from',
                labels={"name_from": "Entities"},
                title=plot_title
            )
        # add the hover
        hover_template = [
            "%{customdata[0]}",
            "%{customdata[1]}",
            "<a href=\"%{customdata[3]}\">Click to view collaboration paper(s)</a>",
            "%{customdata[2]} co-authored paper(s)",
        ]
        fig.update_traces(
            hovertemplate="<br>".join(hover_template),
            marker=dict(
                opacity=1,
                sizemode='area',
                sizeref=markers_size_scale,
                line=dict(
                    color="blue",
                    width=0
                )
            ),
        )
        fig.update_layout(title_x=0.5, spikedistance=40)
        fig.update_geos(
            visible=False,
            showcountries=True,
            showland=True,
        )
        # add a marker for each institution in the list of entities_from
        for i, entity in enumerate(self.collaborations_with_institutions_df.id_from.unique()):
            if get_entity_type_from_id(entity) == Institutions:
                fig.add_scattergeo(
                    mode="markers",
                    lat=[self.collaborations_with_institutions_entities_from_metadata.at[entity, 'lat']],
                    lon=[self.collaborations_with_institutions_entities_from_metadata.at[entity, 'lon']],
                    visible = True,
                    marker=dict(
                        color=fig.data[i].marker.color,
                        opacity=1,
                        size=15,
                        line=dict(width=2, color="DarkSlateGrey"),
                        symbol="diamond"
                    ),
                    hovertemplate=[self.collaborations_with_institutions_entities_from_metadata.at[entity, 'name']],
                    name="",
                    showlegend=False
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
            "Concept score (" + Concepts()[concept]['display_name'] + "): %{customdata[5]}",
        ]
        return hover_template


    def get_figure_nb_time_used(self, element_type: str) -> go.Figure:
        """
        Gets the figure with the number of time each reference is used in a list of works. Also work with concepts.

        :param element_type: The element type ('reference' or 'concept').
        :type element_type: str
        :return: The figure.
        :rtype: go.Figure
        """
        n_x = 2000  # x resolution of the plot
        references_works_count = self.get_element_count(element_type=element_type)
        x_references_works_count = np.geomspace(1, len(references_works_count), num=n_x, dtype=int)
        y_references_works_count = [references_works_count[x - 1] for x in x_references_works_count]
        fig = px.line(x=x_references_works_count,
                      y=y_references_works_count,
                      log_x=True,
                      labels={'x': 'Element rank', 'y': 'Number of time used'},
                      title="Number of time the same element is used by the works in " + self.get_name_of_entity(),
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
            count_years=count_years,
            entity_used_ids=entity_used_ids,
            entity_from_ids=entity_from_ids,
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
            count_years=count_years,
            entity_used_ids=entity_used_ids,
            entity_from_ids=entity_from_ids,
        )
        fig = px.line(
            df,
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
            "Concept score (" + Concepts()[concept]['display_name'] + "): %{customdata[4]}",
            "Cited by count: %{customdata[2]}",
            "Cited by average: %{customdata[3]}"
        ]
        return hover_template


class ConceptsPlot(EntitiesPlot, ConceptsAnalysis):
    """
    This class contains specific methods for Concepts plot. Not used for now.
    """
    pass


class TopicsPlot(EntitiesPlot, TopicsAnalysis):
    """
    This class contains specific methods for Topics plot. Not used for now.
    """
    pass


class PublishersPlot(EntitiesPlot, PublishersAnalysis):
    """
    This class contains specific methods for Publishers plot. Not used for now.
    """
    pass
