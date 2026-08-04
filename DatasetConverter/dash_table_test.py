import dash
from dash.dependencies import Input, Output
import dash_html_components as html
import dash_table
import pandas as pd


df = pd.read_csv('https://raw.githubusercontent.com/plotly/datasets/master/gapminder2007.csv')

df[' index'] = range(1, len(df) + 1)

app = dash.Dash(__name__)

PAGE_SIZE = 5

app.layout = html.Div([
        html.H1(children='Chunk Column Count'),
    html.H2("="*50),
    dash_table.DataTable(
    id='datatable-paging',
    columns=[
        {"name": i, "id": i} for i in sorted(df.columns)
    ],
    page_current=0,
    page_size=PAGE_SIZE,
    page_action='custom'
)])


@app.callback(
    Output('datatable-paging', 'data'),
    Input('datatable-paging', "page_current"),
    Input('datatable-paging', "page_size"))
def update_table(page_current,page_size):
    ShowingData = df.iloc[
        page_current*page_size:(page_current+ 1)*page_size
    ].to_dict('records')
    print("ShowingData", ShowingData)
    print("df.columns", df.columns)
    for i in sorted(df.columns):
        A = {"name": i, "id": i}
        print(A)
    return ShowingData


if __name__ == '__main__':
    app.run_server(debug=True, use_reloader=False)