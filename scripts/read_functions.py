import re
import pandas as pd
from tqdm import tqdm
import logging
import pickle

# Behavior reg-ex (regular expression)
# Regular expression (define the expression filenames are searched for)
# '.' single character, matched everything, '*' 0>> occurences, '/' path delimiter, '\d' 0-9 digit,
# '+' 1>> occurences, 'L' here character from filename
# () outcome here: 2 groups, useful for extraction
# [] optional list, eg 1 --> 1
# ? character non or once
behavior_sample_re = re.compile(r".*/(\d\d-\d\d-\d\dL\d+(-\d+)?)-behavior-(.+).csv")

# Lightmicroscopic data reg-ex (regular expression)
lightmicroscope_sample_re = re.compile(r".*/(\d\d-\d\d-\d\dL\d+(-\d+)?)-(.*)-(.*).csv")

# Behavior reg-ex (regular expression)
time_sample_re = re.compile(r".*/(\d\d-\d\d-\d\dL\d+(-\d+)?)-time-(.+).txt")

# Function: readall_behavior iterates through all csv (sorted)
# and appends the files into the list (ls) and returns dictionary
def readall_behavior(all_files, printit=False, behavior_sample_re=behavior_sample_re):

    data = {}
    for filename in tqdm(sorted(all_files), "Reading Behavior Data: "):
        # Find sample ID, file name pattern: YY-MM-DDLXDETAIL.csv,
        # exp_id = DETAIL: several measurements of same sample
        # (cl (closeloop, RGECO/ Chronos), ol (openloop, RGECO/ Chronos),
        # blocks (Raghav: GCaMP/Chrimson))
        # Larva ID: YY-MM-DDLX
        # Look for filename_components, which are true for pattern
        match = behavior_sample_re.match(filename)
        if not match:
            raise ValueError("Unexpected filename format: {}".format(filename))
        filename_components = match.groups()
        # define filename_components sample_id (first group), and exp_id (sec group)
        part_sample_id, _, exp_id = filename_components
        sample_id = "{}-{}".format(part_sample_id, exp_id)

        df = pd.read_csv(filename, index_col=None, header=0, delimiter=";")
        df.fillna(0, inplace=True)  # replace NaN with zero
        df["sample_id"] = sample_id  # add sample_id column
        df["exp_id"] = exp_id  # add exp_id column
        data[sample_id] = df
        # Count 'True' for each column ('behavior') in each single behavior.csv)
        # print(filename, df[df == 1].count())
        # print(df)

    df_behavior = pd.concat(
        data.values(), axis=0, ignore_index=True, sort=False
    )  # add sorting
    logging.info("Behavior counts:\n{}".format(df_behavior[df_behavior == 1].count()))
    return data


# Function: readall_lm iterates through all LM_csv (sorted)
# and returns a dictionary{key:value}
# samples = {sample_id:cell-id}
def readall_lm(all_files, lightmicroscope_sample_re=lightmicroscope_sample_re):
    # Import and merge fluorescence data: Several LM files for the same sample_id exists, but differ in cell_id).
    # List of LM data with two extra columns: sample_id and cell_id
    # Open LM files from different directories

    # creates mapping from sample id to list of data and experiment id
    samples = {}
    for filename in tqdm(sorted(all_files), "Reading Light Data: "):
        # Find sample ID, file name pattern: YY-MM-DDLXDETAIL.csv,
        # Larva ID: YY-MM-DDLX, DETAIL = cell_id
        # Look for filename_components, which are true for pattern
        match = lightmicroscope_sample_re.match(filename)
        if not match:
            raise ValueError("Unexpected filename format: {}".format(filename))
        filename_components = match.groups()
        part_sample_id, _, cell_id, exp_id = filename_components

        sample_id = "{}-{}".format(part_sample_id, exp_id)

        # Read LM.files
        df = pd.read_csv(filename, index_col=None, header=0, delimiter=",")
        # Replace NaN with zero
        df.fillna(0, inplace=True)

        # Add cellname to each column as prefix
        # lambda is a non defined function (longer version: def lambda(x):)
        # Rename of columns after the format cell_id, name) eg: Basin A9
        # inplace = True: column names are overwritten (if False: new dataframe)
        df.rename(lambda x: "{}_{}".format(cell_id, x), axis="columns", inplace=True)
        # Get the sample_id (key) from the dictionary? to make a list [sample_cells] and
        # if sample_id exists, append the list
        # if sample_id does not exists, start a new list
        # reminder: there can be several cell_id per sample_id
        sample_cells = samples.get(sample_id)
        if not sample_cells:
            samples[sample_id] = sample_cells = {"data": [], "exp_id": exp_id}
        sample_cells["data"].append(df)

    lm_data = {}

    # Iterate over all light samples and merge all found files
    # for each sample into a single data frame (per sample)
    for sample_id, sample_info in samples.items():
        cells_dataframes = sample_info["data"]
        # check if number of cells >= 1
        if not cells_dataframes:
            raise ValueError("No cells found for sample {}".format(sample_id))
        # first element in the list
        lm_df = None

        # iteration through other df
        for cdf in cells_dataframes:
            if lm_df is None:
                lm_df = cdf
            else:
                if len(lm_df.index) != len(cdf.index):
                    raise ValueError(
                        "Data frame frame to merge has not same row count as target",
                        sample_id,
                    )
                lm_df = pd.merge(lm_df, cdf, left_index=True, right_index=True)

        lm_df["sample_id"] = sample_id  # add sample_id column
        lm_df["exp_id"] = sample_info["exp_id"]
        lm_data[sample_id] = lm_df

    return lm_data


# Function: readall_timelapse iterates through all txt (sorted) and appends the
# files into the dict (data) and returns ls
def readall_time(
    all_files, printit=False, timelapse_cache="timelapse.cache", use_time_cache=True
):
    # Import txt-files from of the absolute time/frame from the Ca-imaging (lm_data).
    # Time-data are combined with sample-ID and experiment-ID.

    try:
        if not use_time_cache:
            raise FileNotFoundError()
        with open(timelapse_cache, "rb") as timelapse_cache_file:
            # TODO ask Tom about ast
            return pickle.load(timelapse_cache_file)
            # cache_data = timelapse_cache_file.read()
            # time_data = ast.literal_eval(cache_data)
    except FileNotFoundError:
        print("No cache file found, recomputing")
        data = {}
        for filename in tqdm(sorted(all_files), "Reading Time Data: "):
            # Find sample ID, file name pattern: YY-MM-DDLXDETAIL.csv,
            # exp_id = DETAIL: several measurements of same sample (cl (closeloop), ol (openloop), blocks (Raghav))
            # Larva ID: YY-MM-DDLX
            # look for filename_components, which are true for pattern
            match = time_sample_re.match(filename)
            if not match:
                raise ValueError("Unexpected filename format: {}".format(filename))
            filename_components = match.groups()
            part_sample_id, _, exp_id = (
                filename_components
            )  # define filename_components sample_id (first group), and exp_id (sec group)
            sample_id = "{}-{}".format(part_sample_id, exp_id)

            df = pd.read_csv(filename, header=1, index_col=None, delim_whitespace=True)
            df = df.T  # transposing because read_csv imports as row
            df = df.reset_index()  # transpose function sets data as index
            df.rename(
                columns={"index": "time"}, inplace=True
            )  # rename reset index column to time
            df["time"] = df.time.astype(float)
            data[sample_id] = df
        # Write cache
        with open(timelapse_cache, "wb") as timelapse_cache_file:
            pickle.dump(data, timelapse_cache_file)
        return data
