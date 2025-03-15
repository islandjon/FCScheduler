import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

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
        description = f"Game scheduled on {row['DATE']} at {row['TIME']}, duration: {row['DURATION']} minutes."
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
            "Start": filtered["Start"].dt.strftime("%I:%M %p"),
            "End": filtered["End"].dt.strftime("%I:%M %p"),
            "Duration (min)": filtered["DURATION"],
            "Location": filtered["LOCATION"]
        })
        st.subheader("Filtered Schedule")
        st.table(display_df)
        
        # --- Conflict Detection (Overlapping or within 30 minutes) ---
        conflicts = []
        rows = filtered.to_dict("records")
        for i in range(len(rows)):
            for j in range(i+1, len(rows)):
                r1, r2 = rows[i], rows[j]
                if r1["DATE"] == r2["DATE"]:
                    gap = r2["Start"] - r1["End"]
                    if gap <= timedelta(minutes=30):
                        conflict_type = "Overlapping" if gap.total_seconds() < 0 else "Close (within 30 minutes)"
                        conflicts.append((r1, r2, conflict_type, gap))
        
        st.subheader("Conflicts")
        if conflicts:
            for idx, (game1, game2, conflict_type, gap) in enumerate(conflicts, 1):
                with st.expander(f"Conflict {idx} on {game1['DATE']} – {conflict_type}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Game 1**")
                        st.write(f"**Match:** {game1['HOME TEAM']} vs {game1['AWAY TEAM']}")
                        st.write(f"**Time:** {game1['TIME']} - {game1['End'].strftime('%I:%M %p')}")
                        st.write(f"**Location:** {game1['LOCATION']}")
                    with col2:
                        st.markdown("**Game 2**")
                        st.write(f"**Match:** {game2['HOME TEAM']} vs {game2['AWAY TEAM']}")
                        st.write(f"**Time:** {game2['TIME']} - {game2['End'].strftime('%I:%M %p')}")
                        st.write(f"**Location:** {game2['LOCATION']}")
                    st.write(f"**Gap:** {abs(gap)}")
        else:
            st.success("No overlapping or close matches (within 30 minutes) for the selected teams.")
        
        # --- Generate Calendar File ---
        ics_content = generate_ics(filtered)
        st.download_button(
            label="Download Calendar (.ics)",
            data=ics_content,
            file_name="filtered_schedule.ics",
            mime="text/calendar",
        )
else:
    st.info("Please upload an Excel file to begin.")
