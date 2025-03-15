import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import csv

st.set_page_config(layout='wide')

# --- Helper Functions ---
def safe_parse_datetime(date_val, time_val):
    if pd.isna(date_val) or pd.isna(time_val):
        return None
    try:
        # Convert date_val to datetime if not already.
        if not isinstance(date_val, datetime):
            date_dt = pd.to_datetime(date_val)
        else:
            date_dt = date_val
        # Process time_val.
        if isinstance(time_val, str):
            time_parsed = None
            for fmt in ["%I:%M %p", "%H:%M", "%H:%M:%S"]:
                try:
                    time_parsed = datetime.strptime(time_val, fmt).time()
                    break
                except ValueError:
                    continue
            if time_parsed is None:
                return None
        elif isinstance(time_val, datetime):
            time_parsed = time_val.time()
        else:
            time_parsed = time_val  # Assume already a time object.
        return datetime.combine(date_dt.date(), time_parsed)
    except Exception:
        return None

@st.cache_data
def load_data(uploaded_file):
    df = pd.read_excel(uploaded_file)
    # Drop preexisting "Start" and "End" columns if present.
    df = df.drop(columns=["Start", "End"], errors="ignore")
    # Clean team columns.
    df["HOME TEAM"] = df["HOME TEAM"].astype(str).str.strip()
    df["AWAY TEAM"] = df["AWAY TEAM"].astype(str).str.strip()
    # Parse datetime using the safe parser.
    df["Start"] = df.apply(lambda row: safe_parse_datetime(row["DATE"], row["TIME"]), axis=1)
    df = df.dropna(subset=["Start"]).copy()
    df["Start"] = pd.to_datetime(df["Start"])
    # Calculate End time (assuming DURATION is in minutes)
    df["End"] = df["Start"] + pd.to_timedelta(df["DURATION"].astype(float), unit="m")
    return df

def generate_ics(filtered_df):
    """
    Generate an ICS calendar file as a string from the filtered schedule DataFrame.
    """
    cal = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Soccer Schedule//EN\n"
    # Use current UTC time for dtstamp.
    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for i, row in filtered_df.iterrows():
        uid = f"event-{i}@soccerschedule.com"
        # Here we assume that Start/End are local times; we format without trailing 'Z'.
        dtstart = row["Start"].strftime("%Y%m%dT%H%M%S")
        dtend   = row["End"].strftime("%Y%m%dT%H%M%S")
        summary = f"{row['HOME TEAM']} vs {row['AWAY TEAM']}"
        location = row["LOCATION"]
        description = f"Game scheduled on {row['DATE'].strftime("%d %b %Y")} at {row['TIME']}, duration: {row['DURATION']} minutes."
        cal += (
            "BEGIN:VEVENT\n"
            f"UID:{uid}\n"
            f"DTSTAMP:{dtstamp}\n"
            f"DTSTART:{dtstart}\n"
            f"DTEND:{dtend}\n"
            f"SUMMARY:{summary}\n"
            f"LOCATION:{location}\n"
            f"DESCRIPTION:{description}\n"
            "END:VEVENT\n"
        )
    cal += "END:VCALENDAR\n"
    return cal

def generate_teamsnap_csv(schedule_df, our_team):
    """
    Create a TeamSnap-compatible CSV as a string for a single 'our_team'.
    TeamSnap columns (in order):
    Date,Time,Duration (HH:MM),Arrival Time (Minutes),Name,Opponent Name,
    Opponent Contact Name,Opponent Contact Phone Number,Opponent Contact E-mail Address,
    Location Name,Location Address,Location Details,Location URL,Home or Away,
    Uniform,Extra Label,Notes
    """
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Date",
        "Time",
        "Duration (HH:MM)",
        "Arrival Time (Minutes)",
        "Name",
        "Opponent Name",
        "Opponent Contact Name",
        "Opponent Contact Phone Number",
        "Opponent Contact E-mail Address",
        "Location Name",
        "Location Address",
        "Location Details",
        "Location URL",
        "Home or Away",
        "Uniform",
        "Extra Label",
        "Notes"
    ])

    for _, row in schedule_df.iterrows():
        # Convert date/time
        start_dt = row["Start"]
        date_str = start_dt.strftime("%m/%d/%Y")
        time_str = start_dt.strftime("%I:%M %p").lstrip("0")
        
        # Convert numeric DURATION (minutes) to "HH:MM"
        dur_minutes = int(row["DURATION"])
        hh = dur_minutes // 60
        mm = dur_minutes % 60
        duration_str = f"{hh}:{mm:02d}"

        # Determine if 'our_team' is home or away
        if row["HOME TEAM"] == our_team:
            home_away_flag = "h"
            opponent_name = row["AWAY TEAM"]
        else:
            home_away_flag = "a"
            opponent_name = row["HOME TEAM"]

        # Example logic: "Home uniform" vs "Away uniform"
        uniform_str = "Home uniform" if home_away_flag == "h" else "Away uniform"

        # Hard-code or customize these fields
        arrival_time = 30
        event_name = "Game"  # or "Practice" if your data indicates so
        opponent_contact_name = ""
        opponent_contact_phone = ""
        opponent_contact_email = ""
        location_address = ""
        location_details = ""
        location_url = ""
        extra_label = ""
        notes = ""

        writer.writerow([
            date_str,
            time_str,
            duration_str,
            arrival_time,
            event_name,
            opponent_name,
            opponent_contact_name,
            opponent_contact_phone,
            opponent_contact_email,
            row["LOCATION"],
            location_address,
            location_details,
            location_url,
            home_away_flag,
            uniform_str,
            extra_label,
            notes
        ])
    return output.getvalue()

# --- Streamlit App ---
st.title("Soccer Schedule Conflict Checker")

uploaded_file = st.file_uploader("Upload your schedule Excel file", type=["xlsx", "xls"])
if uploaded_file is not None:
    df = load_data(uploaded_file)
    
    # Get unique teams.
    all_teams = sorted(set(df["HOME TEAM"]) | set(df["AWAY TEAM"]))
    selected_teams = st.multiselect("Select 2 or more teams to check for overlaps:", all_teams)
    
    if len(selected_teams) < 2:
        st.info("Please select at least two teams to view conflicts.")
    else:
        # Filter schedule.
        mask = df["HOME TEAM"].isin(selected_teams) | df["AWAY TEAM"].isin(selected_teams)
        filtered = df[mask].copy().sort_values("Start")
        
        # --- Display a nicer schedule ---
        display_df = pd.DataFrame({
            "Date": filtered["DATE"],
            "Match": filtered["HOME TEAM"] + " vs " + filtered["AWAY TEAM"],
            "Start": filtered["Start"],
            "End": filtered["End"],
            "Duration (min)": filtered["DURATION"],
            "Location": filtered["LOCATION"]
        })
        display_df = display_df.style.format({'Date': '{:%d %b %Y}','Start': '{:%I:%M %p}', 'End': '{:%I:%M %p}'})
        st.subheader("Filtered Schedule")
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # --- Conflict Detection (Overlapping or within 30 minutes) ---
        conflicts = []
        rows = filtered.to_dict("records")
        for i in range(len(rows)):
            for j in range(i+1, len(rows)):
                r1, r2 = rows[i], rows[j]
                if r1["DATE"] == r2["DATE"]:
                    # Check if games occur at exactly the same time.
                    if r1["Start"] == r2["Start"] and r1["End"] == r2["End"]:
                        conflict_type = "Same Time"
                        gap = timedelta(0)
                        conflicts.append((r1, r2, conflict_type, gap))
                    else:
                        gap = r2["Start"] - r1["End"]
                        if gap <= timedelta(minutes=30):
                            conflict_type = "Overlapping" if gap.total_seconds() < 0 else "Close (within 30 minutes)"
                            conflicts.append((r1, r2, conflict_type, gap))

        st.subheader("Conflicts")
        if conflicts:
            for idx, (game1, game2, conflict_type, gap) in enumerate(conflicts, 1):
                with st.expander(f"Conflict {idx} on {game1['DATE'].strftime('%d %b %Y')} – {conflict_type}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Game 1**")
                        st.write(f"**Match:** {game1['HOME TEAM']} vs {game1['AWAY TEAM']}")
                        st.write(f"**Time:** {game1['Start'].strftime('%I:%M %p')} - {game1['End'].strftime('%I:%M %p')}")
                        st.write(f"**Location:** {game1['LOCATION']}")
                    with col2:
                        st.markdown("**Game 2**")
                        st.write(f"**Match:** {game2['HOME TEAM']} vs {game2['AWAY TEAM']}")
                        st.write(f"**Time:** {game2['Start'].strftime('%I:%M %p')} - {game2['End'].strftime('%I:%M %p')}")
                        st.write(f"**Location:** {game2['LOCATION']}")
                    gap_minutes = int(abs(gap.total_seconds()) // 60)
                    if conflict_type == "Same Time":
                        gap_str = "Both games at the same time"
                    elif gap.total_seconds() < 0:
                        gap_str = f"Overlap by {gap_minutes} minutes"
                    else:
                        gap_str = "No gap" if gap_minutes == 0 else f"Gap of {gap_minutes} minutes"
                    st.write(f"**Gap:** {gap_str}")
        else:
            st.success("No overlapping, same time, or close matches (within 30 minutes) for the selected teams.")


        
        # --- Generate Calendar File ---
        ics_content = generate_ics(filtered)
        st.download_button(
            label="Download Calendar for All Selected Teams (.ics)",
            data=ics_content,
            file_name="filtered_schedule.ics",
            mime="text/calendar",
        )

        # If multiple teams are selected, we generate a separate CSV for each.
        for team in selected_teams:
            st.subheader(f"Team: {team}")
            
            # Filter rows where this team is either home or away
            mask = (df["HOME TEAM"] == team) | (df["AWAY TEAM"] == team)
            team_schedule = df[mask].sort_values("Start")

            # Show the schedule in a small table
            team_schedule['DATE_'] = team_schedule['DATE'].dt.strftime("%d %b %Y")

            st.dataframe(team_schedule[["DATE", "TIME", "DURATION", "HOME TEAM", "AWAY TEAM", "LOCATION"]].style.format({'DATE': '{:%d %b %Y}','TIME': '{:%I:%M %p}'}), use_container_width=True, hide_index=True)

            # Create the CSV content for that single team
            csv_str = generate_teamsnap_csv(team_schedule, our_team=team)

            ics_content = generate_ics(filtered)
            
            st.download_button(
                label=f"Download Calendar for {team} (.ics)",
                data=ics_content,
                file_name=f"{team}_schedule.ics",
                mime="text/calendar",
            )

            # Provide a download button for that team's CSV
            st.download_button(
                label=f"Download TeamSnap CSV for {team}",
                data=csv_str,
                file_name=f"{team}_teamsnap.csv",
                mime="text/csv"
            )
else:
    st.info("Please upload an Excel file to begin.")
