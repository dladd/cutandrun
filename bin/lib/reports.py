#!/usr/bin/env python
# coding: utf-8

import os
import glob
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.ticker import FuncFormatter
import seaborn as sns
import pyranges as pr
import pysam
import time

class Reports:
    data_table = None
    frag_hist = None
    frag_violin = None
    frag_bin500 = None
    seacr_beds = None
    bams = None

    def __init__(self, logger, meta, raw_frags, bin_frag, seacr_bed, bams):
        self.logger = logger
        self.meta_path = meta
        self.raw_frag_path = raw_frags
        self.bin_frag_path = bin_frag
        self.seacr_bed_path = seacr_bed
        self.bam_path = bams

        sns.set()
        sns.set_theme()
        sns.set_context("paper")

    #*
    #========================================================================================
    # UTIL
    #========================================================================================
    #*/

    def format_millions(self, x, pos):
        #the two args are the value and tick position
        return '%1.1fM' % (x * 1e-6)

    def format_thousands(self, x, pos):
        #the two args are the value and tick position
        return '%1.1fK' % (x * 1e-3)

    #*
    #========================================================================================
    # LOAD DATA
    #========================================================================================
    #*/

    def load_data(self):
        # ---------- Data - data_table --------- #
        self.data_table = pd.read_csv(self.meta_path, sep=',')
        self.duplicate_info = False
        if 'dedup_percent_duplication' in self.data_table.columns:
            self.duplicate_info = True

        # ---------- Data - Raw frag histogram --------- #
        # Create list of deeptools raw fragment files
        dt_frag_list = glob.glob(self.raw_frag_path)

        for i in list(range(len(dt_frag_list))):
            # create dataframe from csv file for each file and save to a list
            dt_frag_i = pd.read_csv(dt_frag_list[i], sep='\t', header=None, names=['Size','Occurrences'])
            frag_base_i = os.path.basename(dt_frag_list[i])
            sample_id = frag_base_i.split(".")[0]
            sample_id_split = sample_id.split("_")
            rep_i = sample_id_split[len(sample_id_split)-1]
            group_i ="_".join(sample_id_split[0:(len(sample_id_split)-1)])

            # create long forms of fragment histograms
            dt_frag_i_long = np.repeat(dt_frag_i['Size'].values, dt_frag_i['Occurrences'].values)
            dt_group_i_long = np.repeat(group_i, len(dt_frag_i_long))
            dt_rep_i_long = np.repeat(rep_i, len(dt_frag_i_long))

            dt_group_i_short = np.repeat(group_i, dt_frag_i.shape[0])
            dt_rep_i_short = np.repeat(rep_i, dt_frag_i.shape[0])

            if i==0:
                frags_arr = dt_frag_i_long
                group_arr = dt_group_i_long
                rep_arr = dt_rep_i_long

                group_short = dt_group_i_short
                rep_short = dt_rep_i_short
                self.frag_hist = dt_frag_i
            else:
                frags_arr = np.append(frags_arr, dt_frag_i_long)
                group_arr = np.append(group_arr, dt_group_i_long)
                rep_arr = np.append(rep_arr, dt_rep_i_long)

                group_short = np.append(group_short, dt_group_i_short)
                rep_short = np.append(rep_short, dt_rep_i_short)
                self.frag_hist = self.frag_hist.append(dt_frag_i)

        self.frag_hist['group'] = group_short
        self.frag_hist['replicate'] = rep_short
        self.frag_violin = pd.DataFrame( { "fragment_size" : frags_arr, "group" : group_arr , "replicate": rep_arr} ) #, index = np.arange(len(frags_arr)))

        # ---------- Data - Binned frags --------- #
        # create full join data frame for count data
        # start by creating list of bin500 files
        dt_bin_frag_list = glob.glob(self.bin_frag_path)
        for i in list(range(len(dt_bin_frag_list))):
            dt_bin_frag_i_read = pd.read_csv(dt_bin_frag_list[i], sep='\t', header=None, names=['chrom','bin','count','sample'])
            sample_name = dt_bin_frag_i_read['sample'].iloc[0].split(".")[0]
            dt_bin_frag_i = dt_bin_frag_i_read[['chrom','bin','count']]
            dt_bin_frag_i.columns = ['chrom','bin',sample_name]

            if i==0:
                self.frag_bin500 = dt_bin_frag_i

            else:
                self.frag_bin500 = pd.merge(self.frag_bin500, dt_bin_frag_i, on=['chrom','bin'], how='outer')

        # add log2 transformed count data column
        log2_counts = self.frag_bin500[self.frag_bin500.columns[-(len(dt_bin_frag_list)):]].transform(lambda x: np.log2(x))
        chrom_bin_cols = self.frag_bin500[['chrom','bin']]
        self.frag_bin500 = pd.concat([chrom_bin_cols,log2_counts], axis=1)

        # ---------- Data - Peaks --------- #
        # create dataframe for seacr peaks
        seacr_bed_list = glob.glob(self.seacr_bed_path)

        # combine all seacr bed files into one df including group and replicate info
        for i in list(range(len(seacr_bed_list))):
            seacr_bed_i = pd.read_csv(seacr_bed_list[i], sep='\t', header=None, usecols=[0,1,2,3,4], names=['chrom','start','end','total_signal','max_signal'])
            bed_base_i = os.path.basename(seacr_bed_list[i])
            sample_id = bed_base_i.split(".")[0]
            sample_id_split = sample_id.split("_")
            rep_i = sample_id_split[len(sample_id_split)-1]
            group_i ="_".join(sample_id_split[0:(len(sample_id_split)-1)])
            seacr_bed_i['group'] = np.repeat(group_i, seacr_bed_i.shape[0])
            seacr_bed_i['replicate'] = np.repeat(rep_i, seacr_bed_i.shape[0])

            if i==0:
                self.seacr_beds = seacr_bed_i

            else:
                self.seacr_beds = self.seacr_beds.append(seacr_bed_i)

        # ---------- Data - target histone mark bams --------- #
        bam_list = glob.glob(self.bam_path)
        self.bam_df_list = list()
        self.frip = pd.DataFrame(data=None, index=range(len(bam_list)), columns=['group','replicate','mapped_frags','frags_in_peaks','percentage_frags_in_peaks'])
        k = 0 #counter

        def pe_bam_to_df(bam_path):
            bamfile = pysam.AlignmentFile(bam_path, "rb")
            # Iterate through reads.
            read1 = None
            read2 = None
            k=0 #counter

            # get number of reads in bam
            count = 0
            for _ in bamfile:
                count += 1

            bamfile.close()
            bamfile = pysam.AlignmentFile(bam_path, "rb")

            # initialise arrays
            frag_no = round(count/2)
            start_arr = np.zeros(frag_no, dtype=np.int64)
            end_arr = np.zeros(frag_no, dtype=np.int64)
            chrom_arr = np.empty(frag_no, dtype="<U20")

            for read in bamfile:

                if not read.is_paired or read.mate_is_unmapped or read.is_duplicate:
                    continue

                if read.is_read2:
                    read2 = read
                    # print("is read2: " + read.query_name)

                else:
                    read1 = read
                    read2 = None
                    # print("is read1: " + read.query_name)

                if read1 is not None and read2 is not None and read1.query_name == read2.query_name:

                    start_pos = min(read1.reference_start, read2.reference_start)
                    end_pos = max(read1.reference_end, read2.reference_end) - 1
                    chrom = read.reference_name

                    start_arr[k] = start_pos
                    end_arr[k] = end_pos
                    chrom_arr[k] = chrom

                    k +=1

            bamfile.close()

            # remove zeros and empty elements. The indicies for these are always the same from end_arr and chrom_arr
            remove_idx = np.where(chrom_arr == '')[0]
            chrom_arr = np.delete(chrom_arr, remove_idx)
            start_arr = np.delete(start_arr, remove_idx)
            end_arr = np.delete(end_arr, remove_idx)

            # create dataframe
            bam_df = pd.DataFrame({ "Chromosome" : chrom_arr, "Start" : start_arr, "End" : end_arr })
            return(bam_df)

        for bam in bam_list:
            bam_now = pe_bam_to_df(bam)
            self.bam_df_list.append(bam_now)
            bam_base = os.path.basename(bam)
            sample_id = bam_base.split(".")[0]
            [group_now,rep_now] = sample_id.split("_")
            self.frip.at[k, 'group'] = group_now
            self.frip.at[k, 'replicate'] = rep_now
            self.frip.at[k, 'mapped_frags'] = bam_now.shape[0]
            k=k+1

        # ---------- Data - New frag_hist --------- #
        for i in list(range(len(self.bam_df_list))):
            df_i = self.bam_df_list[i]
            widths_i = (df_i['End'] - df_i['Start']).abs()
            unique_i, counts_i = np.unique(widths_i, return_counts=True)
            group_i = np.repeat(self.frip.at[i, 'group'], len(unique_i))
            rep_i = np.repeat(self.frip.at[i, 'replicate'], len(unique_i))

            if i==0:
                frag_lens = unique_i
                frag_counts = counts_i
                group_arr = group_i
                rep_arr = rep_i
            else:
                frag_lens = np.append(frag_lens, unique_i)
                frag_counts = np.append(frag_counts, counts_i)
                group_arr = np.append(group_arr, group_i)
                rep_arr = np.append(rep_arr, rep_i)

        self.frag_series = pd.DataFrame({'group' : group_arr, 'replicate' : rep_arr, 'frag_len' : frag_lens, 'occurences' : frag_counts})

        # ---------- Data - Peak stats --------- #
        # create number of peaks df
        unique_groups = self.seacr_beds.group.unique()
        unique_replicates = self.seacr_beds.replicate.unique()
        self.df_no_peaks = pd.DataFrame(index=range(0,(len(unique_groups)*len(unique_replicates))), columns=['group','replicate','all_peaks'])
        k=0 # counter

        for i in list(range(len(unique_groups))):
            for j in list(range(len(unique_replicates))):
                self.df_no_peaks.at[k,'all_peaks'] = self.seacr_beds[(self.seacr_beds['group']==unique_groups[i]) & (self.seacr_beds['replicate']==unique_replicates[j])].shape[0]
                self.df_no_peaks.at[k,'group'] = unique_groups[i]
                self.df_no_peaks.at[k,'replicate'] = unique_replicates[j]
                k=k+1

        # ---------- Data - Reproducibility of peaks between replicates --------- #
        # empty dataframe to fill in loop
        self.reprod_peak_stats = self.df_no_peaks
        self.reprod_peak_stats = self.reprod_peak_stats.reindex(columns=self.reprod_peak_stats.columns.tolist() + ['no_peaks_reproduced','peak_reproduced_rate'])

        # create permutations list
        def array_permutate(x):
            arr_len=len(x)
            loop_list = x
            out_list = x
            for i in range(arr_len-1):
                i_list = np.roll(loop_list, -1)
                out_list = np.vstack((out_list, i_list))
                loop_list = i_list
            return out_list

        # create pyranges objects and fill df
        unique_groups = self.seacr_beds.group.unique()
        unique_replicates = self.seacr_beds.replicate.unique()
        rep_permutations = array_permutate(range(len(unique_replicates)))
        self.replicate_number = len(unique_replicates)

        if self.replicate_number > 1:
            idx_count=0
            for i in list(range(len(unique_groups))):
                group_i = unique_groups[i]
                for k in list(range(len(unique_replicates))):
                    pyr_query = pr.PyRanges()
                    rep_perm = rep_permutations[k]
                    for j in rep_perm:
                        rep_i = unique_replicates[j]
                        peaks_i = self.seacr_beds[(self.seacr_beds['group']==group_i) & (self.seacr_beds['replicate']==rep_i)]
                        pyr_subject = pr.PyRanges(chromosomes=peaks_i['chrom'], starts=peaks_i['start'], ends=peaks_i['end'])
                        if(len(pyr_query) > 0):
                            pyr_overlap = pyr_query.join(pyr_subject)
                            pyr_overlap = pyr_overlap.apply(lambda df: df.drop(['Start_b','End_b'], axis=1))
                            pyr_query = pyr_overlap

                        else:
                            pyr_query = pyr_subject

                    pyr_starts = pyr_overlap.values()[0]['Start']
                    unique_pyr_starts = pyr_starts.unique()
                    self.reprod_peak_stats.at[idx_count, 'no_peaks_reproduced'] = len(unique_pyr_starts)
                    idx_count = idx_count + 1

            fill_reprod_rate = (self.reprod_peak_stats['no_peaks_reproduced'] / self.reprod_peak_stats['all_peaks'])*100
            self.reprod_peak_stats['peak_reproduced_rate'] = fill_reprod_rate

        # ---------- Data - Percentage of fragments in peaks --------- #
        for i in range(len(self.bam_df_list)):
            bam_i = self.bam_df_list[i]
            self.frip.at[i,'mapped_frags'] = bam_i.shape[0]
            group_i = self.frip.at[i,'group']
            rep_i = self.frip.at[i,'replicate']
            seacr_bed_i = self.seacr_beds[(self.seacr_beds['group']==group_i) & (self.seacr_beds['replicate']==rep_i)]
            pyr_seacr = pr.PyRanges(chromosomes=seacr_bed_i['chrom'], starts=seacr_bed_i['start'], ends=seacr_bed_i['end'])
            pyr_bam = pr.PyRanges(df=bam_i)
            sample_id = group_i + "_" + rep_i
            frag_count_pyr = pyr_bam.count_overlaps(pyr_seacr)
            frag_counts = np.count_nonzero(frag_count_pyr.NumberOverlaps)

            self.frip.at[i,'frags_in_peaks'] = frag_counts

        self.frip['percentage_frags_in_peaks'] = (self.frip['frags_in_peaks'] / self.frip['mapped_frags'])*100

    def annotate_data_table(self):
        # Make new perctenage alignment columns
        self.data_table['target_alignment_rate'] = self.data_table.loc[:, ('bt2_total_aligned_target')] / self.data_table.loc[:, ('bt2_total_reads_target')] * 100
        self.data_table['spikein_alignment_rate'] = self.data_table.loc[:, ('bt2_total_aligned_spikein')] / self.data_table.loc[:, ('bt2_total_reads_spikein')] * 100

    #*
    #========================================================================================
    # GEN REPORTS
    #========================================================================================
    #*/

    def generate_plots(self):
        # Init
        plots = dict()
        data = dict()

        # Get Data
        self.load_data()
        self.annotate_data_table()

        # Plot 1
        plot1, data1 = self.alignment_summary()
        plots["alignment_summary"] = plot1
        data["alignment_summary"] = data1

        # Plot 2
        if self.duplicate_info == True:
            plot2, data2 = self.duplication_summary()
            plots["duplication_summary"] = plot2
            data["duplication_summary"] = data2

        # Plot 3
        plot3, data3 = self.fraglen_summary_violin()
        plots["frag_violin"] = plot3
        data["frag_violin"] = data3

        # Plot 4
        plot4, data4 = self.fraglen_summary_histogram()
        plots["frag_hist"] = plot4
        data["frag_hist"] = data4

        # Plot 5
        if self.replicate_number > 1:
            plot5, data5 = self.replicate_heatmap()
            plots["replicate_heatmap"] = plot5
            data["replicate_heatmap"] = data5

        # Plot 6
        plot6, data6 = self.scale_factor_summary()
        plots["scale_factor_summary"] = plot6
        data["scale_factor_summary"] = data6

        # Plot 7a
        plot7a, data7a = self.no_of_peaks()
        plots["no_of_peaks"] = plot7a
        data["no_of_peaks"] = data7a

        # Plot 7b
        plot7b, data7b = self.peak_widths()
        plots["peak_widths"] = plot7b
        data["peak_widths"] = data7b

        # Plot 7c
        if self.replicate_number > 1:
            plot7c, data7c = self.reproduced_peaks()
            plots["reproduced_peaks"] = plot7c
            data["reproduced_peaks"] = data7c

        # Plot 7d
        plot7d, data7d = self.frags_in_peaks()
        plots["frags_in_peaks"] = plot7d
        data["frags_in_peaks"] = data7d

        return (plots, data)

    def gen_plots_to_folder(self, output_path):
        # Init
        abs_path = os.path.abspath(output_path)

        # Get plots and supporting data tables
        plots, data = self.generate_plots()

        # Save data to output folder
        for key in data:
            data[key].to_csv(os.path.join(abs_path, key + '.csv'), index=False)
            plots[key].savefig(os.path.join(abs_path, key + '.png'))

        # Save pdf of the plots
        self.gen_pdf(abs_path, plots)

    def gen_pdf(self, output_path, plots):
        with PdfPages(os.path.join(output_path, 'report.pdf')) as pdf:
            for key in plots:
                pdf.savefig(plots[key])

            # # We can also set the file's metadata via the PdfPages object:
            # d = pdf.infodict()
            # d['Title'] = 'Multipage PDF Example'
            # d['Author'] = 'Jouni K. Sepp\xe4nen'
            #        d['Subject'] = 'How to create a multipage pdf file and set its metadata'
            # d['Keywords'] = 'PdfPages multipage keywords author title subject'
            # d['CreationDate'] = datetime.datetime(2009, 11, 13)
            # d['ModDate'] = datetime.datetime.today()

    #*
    #========================================================================================
    # PLOTS
    #========================================================================================
    #*/

    # ---------- Plot 1 - Alignment Summary --------- #
    def alignment_summary(self):
        sns.color_palette("magma", as_cmap=True)
        sns.set(font_scale=0.6)
        # Subset data
        df_data = self.data_table.loc[:, ('id', 'group', 'bt2_total_reads_target', 'bt2_total_aligned_target', 'target_alignment_rate', 'spikein_alignment_rate')]

        ## Construct quad plot
        fig, seq_summary = plt.subplots(2,2)
        fig.suptitle("Sequencing and Alignment Summary")

        # Seq depth
        sns.boxplot(data=df_data, x='group', y='bt2_total_reads_target', ax=seq_summary[0,0], palette = "magma")
        seq_summary[0,0].set_title("Sequencing Depth")
        seq_summary[0,0].set_ylabel("Total Reads")

        # Alignable fragments
        sns.boxplot(data=df_data, x='group', y='bt2_total_aligned_target', ax=seq_summary[0,1], palette = "magma")
        seq_summary[0,1].set_title("Alignable Fragments")
        seq_summary[0,1].set_ylabel("Total Aligned Reads")

        # Alignment rate hg38
        sns.boxplot(data=df_data, x='group', y='target_alignment_rate', ax=seq_summary[1,0], palette = "magma")
        seq_summary[1,0].set_title("Alignment Rate (Target)")
        seq_summary[1,0].set_ylabel("Percent of Fragments Aligned")

        # Alignment rate e.coli
        sns.boxplot(data=df_data, x='group', y='spikein_alignment_rate', ax=seq_summary[1,1], palette = "magma")
        seq_summary[1,1].set_title("Alignment Rate (Spike-in)")
        seq_summary[1,1].set_ylabel("Percent of Fragments Aligned")

        plt.subplots_adjust(wspace=0.4, hspace=0.45)

        return fig, df_data

    # ---------- Plot 2 - Duplication Summary --------- #
    def duplication_summary(self):
        # Init
        k_formatter = FuncFormatter(self.format_thousands)
        m_formatter = FuncFormatter(self.format_millions)

        # Subset data
        df_data = self.data_table.loc[:, ('id', 'group', 'dedup_percent_duplication', 'dedup_estimated_library_size', 'dedup_read_pairs_examined')]
        df_data['dedup_percent_duplication'] *= 100
        df_data['unique_frag_num'] = df_data['dedup_read_pairs_examined'] * (1-df_data['dedup_percent_duplication']/100)

        ## Construct quad plot
        fig, seq_summary = plt.subplots(1,3)
        fig.suptitle("Duplication Summary")

        # Duplication rate
        sns.boxplot(data=df_data, x='group', y='dedup_percent_duplication', ax=seq_summary[0], palette = "magma")
        seq_summary[0].set_ylabel("Duplication Rate (%)")
        seq_summary[0].set(ylim=(0, 100))
        seq_summary[0].xaxis.set_tick_params(labelrotation=45)

        # Estimated library size
        sns.boxplot(data=df_data, x='group', y='dedup_estimated_library_size', ax=seq_summary[1], palette = "magma")
        seq_summary[1].set_ylabel("Estimated Library Size")
        seq_summary[1].yaxis.set_major_formatter(m_formatter)
        seq_summary[1].xaxis.set_tick_params(labelrotation=45)

        # No. of unique fragments
        sns.boxplot(data=df_data, x='group', y='unique_frag_num', ax=seq_summary[2], palette = "magma")
        seq_summary[2].set_ylabel("No. of Unique Fragments")
        seq_summary[2].yaxis.set_major_formatter(k_formatter)
        seq_summary[2].xaxis.set_tick_params(labelrotation=45)

        # Set the plot sizing
        plt.subplots_adjust(top = 0.9, bottom = 0.2, right = 0.9, left = 0.1, hspace = 0.7, wspace = 0.7)

        return fig, df_data


    # ---------- Plot 3 - Fragment Distribution Violin --------- #
    def fraglen_summary_violin(self):
        fig, ax = plt.subplots()
        ax = sns.violinplot(data=self.frag_violin, x="group", y="fragment_size", hue="replicate", palette = "viridis")
        ax.set(ylabel="Fragment Size")
        fig.suptitle("Fragment Length Distribution")

        return fig, self.frag_violin

    # ---------- Plot 4 - Fragment Distribution Histogram --------- #
    def fraglen_summary_histogram(self):
        fig, ax = plt.subplots()
        # ax = sns.lineplot(data=self.frag_hist, x="Size", y="Occurrences", hue="Sample")
        ax = sns.lineplot(data=self.frag_hist, x="Size", y="Occurrences", hue="group", style="replicate", palette = "magma")
        fig.suptitle("Fragment Length Distribution")

        return fig, self.frag_hist

    def alignment_summary_ex(self):
        df_data = self.data_table.loc[:, ('id', 'group', 'bt2_total_reads_target', 'bt2_total_aligned_target', 'target_alignment_rate', 'spikein_alignment_rate')]

        ax = px.box(df_data, x="group", y="bt2_total_reads_target", palette = "magma")

        return ax, df_data


    # ---------- Plot 5 - Replicate Reproducibility Heatmap --------- #
    def replicate_heatmap(self):
        fig, ax = plt.subplots()
        plot_data = self.frag_bin500[self.frag_bin500.columns[-(len(self.frag_bin500.columns)-2):]]
        # plot_data = plot_data.fillna(0)
        corr_mat = plot_data.corr(method='pearson')
        ax = sns.heatmap(corr_mat, annot=True)
        fig.suptitle("Replicate Reproducibility")

        return fig, self.frag_bin500

    # ---------- Plot 6 - Scale Factor Comparison --------- #
    def scale_factor_summary(self):
        fig, scale_summary = plt.subplots(1,2)
        fig.suptitle("Scaling Factor")

        # Get normalised count data
        df_normalised_frags = self.data_table.loc[:, ('id', 'group')]
        df_normalised_frags['normalised_frags'] = self.data_table['bt2_total_reads_target']*self.data_table['scale_factor']

        # Subset meta data
        df_data_scale = self.data_table.loc[:, ('id', 'group','scale_factor')]

        # Scale factor
        sns.boxplot(data=df_data_scale, x='group', y='scale_factor', ax=scale_summary[0], palette = "magma")
        scale_summary[0].set_ylabel('Scale Factor')

        # Normalised fragment count
        sns.boxplot(data=df_normalised_frags, x='group', y='normalised_frags', ax=scale_summary[1], palette = "magma")
        scale_summary[1].set_ylabel('Normalised Fragment Count')

        return fig, df_data_scale

    # ---------- Plot 7 - Peak Analysis --------- #
    def no_of_peaks(self):
    # 7a - Number of peaks
        fig, ax = plt.subplots()
        fig.suptitle("Total Peaks")

        ax = sns.boxplot(data=self.df_no_peaks, x='group', y='all_peaks', palette = "magma")
        ax.set_ylabel("No. of Peaks")

        return fig, self.df_no_peaks

    # 7b - Width of peaks
    def peak_widths(self):
        fig, ax = plt.subplots()

        ## add peak width column
        self.seacr_beds['peak_width'] = self.seacr_beds['end'] - self.seacr_beds['start']
        self.seacr_beds['peak_width'] = self.seacr_beds['peak_width'].abs()

        ax = sns.violinplot(data=self.seacr_beds, x="group", y="peak_width", hue="replicate", palette = "viridis")
        ax.set_ylabel("Peak Width")
        fig.suptitle("Peak Width Distribution")

        return fig, self.seacr_beds


    # 7c - Peaks reproduced
    def reproduced_peaks(self):
        fig, ax = plt.subplots()

        # plot
        ax = sns.barplot(data=self.reprod_peak_stats, hue="replicate", x="group", y="peak_reproduced_rate", palette = "viridis")
        ax.set_ylabel("Peaks Reproduced (%)")
        fig.suptitle("Peak Reprodducibility")

        return fig, self.reprod_peak_stats

    # 7d - Fragments within peaks
    def frags_in_peaks(self):
        fig, ax = plt.subplots()

        ax = sns.boxplot(data=self.frip, x='group', y='percentage_frags_in_peaks', palette = "magma")
        ax.set_ylabel("Fragments within Peaks (%)")
        fig.suptitle("Aligned Fragments within Peaks")

        return fig, self.frip
