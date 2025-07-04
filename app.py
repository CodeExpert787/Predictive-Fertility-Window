from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
import pandas as pd
import io

app = Flask(__name__)
CORS(app)  # This will allow the frontend to communicate with the backend

def calculate_ovulation_day(lmp_date, cycle_length, has_pcos):
    days_to_ovulation = cycle_length - 14
    if has_pcos:
        days_to_ovulation = int(cycle_length * 0.6)
    
    ovulation_date = lmp_date + timedelta(days=days_to_ovulation)
    return ovulation_date

def calculate_fertile_window(ovulation_day):
    fertile_start = ovulation_day - timedelta(days=5)
    fertile_end = ovulation_day + timedelta(days=1)
    return {'start': fertile_start, 'end': fertile_end}

def analyze_cycle_regularity(cycle_lengths, has_pcos):
    if has_pcos:
        return "Irregular - PCOS may cause irregular cycles"
    if max(cycle_lengths) - min(cycle_lengths) > 8:
        return "Irregular"
    return "Regular"

def calculate_conception_probability(fertile_window):
    probabilities = [
        {'day_offset': -5, 'prob': 'Low (~4%)'},
        {'day_offset': -4, 'prob': 'Low (~10%)'},
        {'day_offset': -3, 'prob': 'Medium (~15%)'},
        {'day_offset': -2, 'prob': 'High (~27%)'},
        {'day_offset': -1, 'prob': 'High (~30%)'},
        {'day_offset': 0, 'prob': 'Peak (~33%)'},
        {'day_offset': 1, 'prob': 'Very Low'}
    ]
    
    probability_list = []
    for i in range(7):
        day = fertile_window['start'] + timedelta(days=i)
        probability_list.append({
            'date': day.strftime('%B %d'),
            'probability': probabilities[i]['prob']
        })
    return probability_list

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/predict', methods=['POST'])
def predict():
    # Data is now in request.form because we are using FormData
    data = request.form
    
    # --- Data Extraction and Processing ---
    name =  data.get('name')
    cycle_lengths = [int(data['cycleLength1']), int(data['cycleLength2']), int(data['cycleLength3'])]
    period_durations = [int(data['periodDuration1']), int(data['periodDuration2']), int(data['periodDuration3'])]
    
    lmp_date_str = data['lmpDate3']
    lmp_date = datetime.strptime(lmp_date_str, '%Y-%m-%d')
    
    # The value from the form will be a string 'true' or 'false'
    has_pcos = data.get('pcos') == 'true'
    
    # Check for an uploaded file if PCOS is true
    if has_pcos:
        bbt_file = request.files.get('bbtFile')
        if bbt_file and bbt_file.filename != '':
            print(f"Received file: {bbt_file.filename}")
            try:
                if bbt_file.filename.lower().endswith('.csv'):
                    df = pd.read_csv(bbt_file)
                else:
                    df = pd.read_excel(bbt_file)
                
                # --- Calculate average BBT for this user ---
                if 'user_id' in df.columns:
                    user_rows = df[df['user_id'] == name]
                    if not user_rows.empty:
                        for col in ['bbt', 'BBT', 'temperature', 'Temperature']:
                            if col in user_rows.columns:
                                avg_bbt = user_rows[col].mean()
                                print(f"Average BBT for user '{name}': {avg_bbt:.2f}")
                                break
                        else:
                            print("No BBT column found in the file.")
                    else:
                        print(f"No rows found for user_id '{name}'.")
                else:
                    print("No 'user_id' column found in the file.")
            except Exception as e:
                print(f"Error reading file: {e}")

    # --- Calculations ---
    avg_cycle_length = round(sum(cycle_lengths) / len(cycle_lengths))
    avg_period_duration = round(sum(period_durations) / len(period_durations))
    
    # Predict the start of the next cycle
    next_lmp_date = lmp_date + timedelta(days=avg_cycle_length)
    
    ovulation_day = calculate_ovulation_day(next_lmp_date, avg_cycle_length, has_pcos)
    fertile_window = calculate_fertile_window(ovulation_day)
    cycle_regularity = analyze_cycle_regularity(cycle_lengths, has_pcos)
    conception_probability = calculate_conception_probability(fertile_window)
    
    # --- Format Response ---
    response = {
        'fertileWindow': {
            'start': fertile_window['start'].strftime('%A, %B %d, %Y'),
            'end': fertile_window['end'].strftime('%A, %B %d, %Y')
        },
        'ovulationDay': ovulation_day.strftime('%A, %B %d, %Y'),
        'cycleRegularity': cycle_regularity,
        'conceptionProbability': conception_probability,
        'insights': {
            'averageCycleLength': avg_cycle_length,
            'averagePeriodDuration': avg_period_duration,
        }
    }
    
    return jsonify(response)

@app.route('/receive_data', methods=['POST'])
def receive_data():
    data = request.form
    name = data.get('name')
    bbt_file = request.files.get('bbtFile_data')
    result = {'success': False, 'message': ''}
    columns_to_load = [
        'LMP_Cycle_1', 'LMP_Cycle_2', 'LMP_Cycle_3',
        'Cycle_Length_1', 'Cycle_Length_2', 'Cycle_Length_3',
        'Period_Duration_1', 'Period_Duration_2', 'Period_Duration_3',
        'is_pcos'
    ]

    if bbt_file and bbt_file.filename != '':
        try:
            # Read the file into a DataFrame
            if bbt_file.filename.lower().endswith('.csv'):
                df = pd.read_csv(bbt_file)
            else:
                df = pd.read_excel(bbt_file)

            # Filter rows where user_id matches name
            if 'user_id' in df.columns:
                user_rows = df[df['user_id'] == name]
                if not user_rows.empty:
                    user_row = user_rows.iloc[0]  # Take the first match
                    for col in columns_to_load:
                        value = user_row.get(col, None)
                        if value is not None:
                            result[col] = str(value)
                        else:
                            result[col] = None
                    result['success'] = True
                    result['message'] = f"Data loaded for user '{name}'."
                else:
                    result['message'] = f"No rows found for user_id '{name}'."
            else:
                result['message'] = "No 'user_id' column found in the file."
        except Exception as e:
            result['message'] = f"Error reading file: {e}"
    else:
        result['message'] = "No file uploaded."
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False) 