MT_style_cell = {
            'textAlign': 'center',
        }
        
MT_style_cell_conditional = [
        {
            'if': {'column_id': "Mission"},
            'width': '500px',
            'minWidth': '500px',
            'maxWidth': '500px',
            'textAlign': 'left',
            'whiteSpace':'normal',
            #'overflow': 'hidden',
            #'textOverflow': 'ellipsis',
        }
    ]+[
        {
            'if': {'column_id': "Expiry Date"},
            'width': '80px',
            'minWidth': '80px',
            'maxWidth': '80px',
            'textAlign': 'center',
            'whiteSpace':'normal',
            #'overflow': 'hidden',
            #'textOverflow': 'ellipsis',
        }
    ]
       
       
Colortable_style_cell={
            'textAlign': 'center',
            'overflow': 'hidden',
            #'textOverflow': 'ellipsis',
            'whiteSpace': 'normal',
            'height': 'auto',
            }


Colortable_style_cell_conditional=[
    {
        'if': {'column_id': "Explaination"},
        'width': '700px',
        'minWidth': '300px',
        'maxWidth': '700px',
        'textAlign': 'left',
        'whiteSpace':'normal',
        #'overflow': 'hidden',
        #'textOverflow': 'ellipsis',
    }
    ]
Colortable_style_header={
    'backgroundColor': 'rgb(230, 230, 230)',
    'fontWeight': 'bold'
}