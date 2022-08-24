'''
Script to visualise QC metrics from VCF files as distributions (all variants).
Can compare True Positives to False positives or compare different samples.

Author: Chris Pyatt
'''

# import libraries
# standard
import argparse
import math
import re
import string
import sys
# 3rd party
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.io as pio
import scipy.stats as st
import vcf


# global variables
VERBOSE = False
# names used several times so let's just save them here
SAMPLE1_NAME = ''
SAMPLE2_NAME = ''


def get_args():
    '''
    Parses command line arguments.

    INPUT
    nothing
    RETURN
    argparse namespace object
    '''
    parser = argparse.ArgumentParser(

    )
    parser.add_argument(
        '--happy',
        help=(
            'filename of hap.py VCF (containing variants and TP/FP calls). '
            'Gzipped.'
        )
    )
    parser.add_argument(
        '--verbose', action='store_true',
        help=(
            'if enabled, reports which requested metrics are not available '
            'in query vcf'
        )
    )
    parser.add_argument(
        '--query', required=True,
        help=(
            'filename of query VCF (containing variants and metric values). '
            'Gzipped. Up to two query sample VCFs may be provided, but if '
            'a hap.py VCF is provided via the --happy option, only one '
            '(matching) query VCF will be accepted. Input data '
            'must be normalised VCF.'
        )
    )
    parser.add_argument(
        '--metrics', default='all',
        help=(
            'list of metrics to be plotted. The list must be comma-separated '
            'with no spaces. By default, all metrics found in the VCF will '
            'be plotted.'
        )
    )
    args = parser.parse_args()
    # exit gracefully if no arguments given
    if not args or not args.query:
        parser.print_help()
        sys.exit(1)
    # set global verbose variable if needed
    if args.verbose:
        global VERBOSE
        VERBOSE = True
    # convert query to list
    args.query = args.query.split(',')
    # exit gracefully if number of input files is incorrect
    if (
        (len(args.query) == 1 and not args.happy)
        or (len(args.query) == 2 and len(args.happy.split(',')) == 1)
        or (len(args.happy.split(',')) > 1)
    ):
        print('Please check you are providing the correct inputs (--help)')
        sys.exit(1)
    else:
        return args


def get_sample_names(sample1, sample2):
    '''
    Takes two input file names (in the format
    samplename-some-metadata-fields.vcf.gz) and stores just
    the sample names as global variables

    INPUT
    2 strings
    RETURN
    nothing
    '''
    allowed = set(
        string.ascii_lowercase + string.digits + string.ascii_uppercase
        )
    sample1_name = re.split('[.-]', sample1)[0]
    sample2_name = re.split('[.-]', sample2)[0]
    assert set(sample1_name) <= allowed, (
        f'{sample1} does not match the expected pattern. Expected something '
        'like samplename-some-metadata.vcf.gz where samplename contains only '
        'alphanumeric characters.'
        )
    assert set(sample2_name) <= allowed, (
        f'{sample2} does not match the expected pattern. Expected something '
        'like samplename-some-metadata.vcf.gz where samplename contains only '
        'alphanumeric characters.'
        )
    global SAMPLE1_NAME
    global SAMPLE2_NAME
    SAMPLE1_NAME = sample1_name
    SAMPLE2_NAME = sample2_name


def check_happy_query_match(happy, query):
    '''
    Checks that the sample name matches between hap.py VCF and query
    VCF (as variants will need to be matched between the two to assign TP/FP)

    INPUT
    2 strings
    RETURN
    assertion error if not matching, otherwise True (boolean)
    '''
    assert happy == query, (
        'hap.py and query vcf sample names do not '
        f'match ({happy} & {query})'
        )
    return True


def check_multiple_query_metrics(query, metrics):
    '''
    Takes list of (2) query VCFs and a list of metrics. Returns all shared
    metrics.

    INPUT
    2 lists of strings
    RETURN
    1 list of strings
    '''
    available_metrics1 = check_metrics(query[0], metrics)
    available_metrics2 = check_metrics(query[1], metrics)
    available_shared_metrics_info = list(
        set(available_metrics1[0]).intersection(available_metrics2[0])
        )
    available_shared_metrics_format = list(
        set(available_metrics1[1]).intersection(available_metrics2[1])
        )
    available_shared_metrics = [available_shared_metrics_info,
                                available_shared_metrics_format]
    return available_shared_metrics


def check_metrics(query, metrics):
    '''
    Checks that all metrics requested are available in query VCF.

    INPUT
    1 string (query filename) and 1 list of strings
    RETURN
    1 list of strings
    '''
    try:
        if metrics == 'all':
            requested_metrics = 'all'
        else:
            requested_metrics = metrics.split(',')
    except Exception as error:
        print(
            '\nError parsing metrics. Please check formatting.'
            f'Error: {error}'
            )
        sys.exit(1)
    try:
        vcf_reader = vcf.Reader(filename=query)
        # parse out metric names - separate info and format metrics in case
        # of identical names (usually DP)
        filtered_info_metrics = []
        filtered_format_metrics = []
        # grab only metrics where the type is float or integer (as
        # others cannot be plotted) and also where the number of values
        # is constrained to 1. The latter constraint will be modified
        # to accept lists of values in later versions of this tool.
        info_metrics = vcf_reader.infos
        for i, j in info_metrics.items():
            if j.type in ('Integer', 'Float') and j.num == 1:
                filtered_info_metrics.append(i)
        format_metrics = vcf_reader.formats
        for i, j in format_metrics.items():
            if j.type in ('Integer', 'Float') and j.num == 1:
                filtered_format_metrics.append(i)
    except Exception as error:
        print(
            '\nError retreiving query VCF metrics. Please check format.\n'
            f'Error: {error}'
            )
        sys.exit(1)
    if requested_metrics == 'all':
        available_info_metrics = filtered_info_metrics
        available_format_metrics = filtered_format_metrics
        unavailable_metrics = [[], []]
    else:
        available_info_metrics = list(
            set(requested_metrics).intersection(filtered_info_metrics)
            )
        available_format_metrics = list(
            set(requested_metrics).intersection(filtered_format_metrics)
            )
        unavailable_info_metrics = list(
            set(requested_metrics).difference(filtered_info_metrics)
            )
        unavailable_format_metrics = list(
            set(requested_metrics).difference(filtered_format_metrics)
            )
        unavailable_metrics = [unavailable_info_metrics,
                               unavailable_format_metrics]
    # add prefixes to metrics list to distinguish duplicate metric names in
    # INFO and FORMAT fields
    available_metrics = []
    available_metrics.extend(f'info_{x}' for x in available_info_metrics)
    available_metrics.extend(f'format_{x}' for x in available_format_metrics)
    if VERBOSE:
        print('\nThe metrics below were requested but not present in the '
              f'query VCF ({query}).\n' + str(unavailable_metrics))
    return available_metrics


def parse_query(query, happy=True):
    '''
    Takes a query vcf filename. Returns a dictionary of relevant
    metrics and values, paired to variants.

    INPUT
    1 string (query filename) and 1 optional boolean
    RETURN
    1 dictionary of dictionaries
    '''
    try:
        vcf_reader = vcf.Reader(filename=query)
        variant_dict = {}
        for record in vcf_reader:
            chrom = record.CHROM
            pos = record.POS
            ref = str(record.REF)
            # take only alt #1 (should only be one anyway) - not worried as
            # alt not used except for dict key
            alt = str(record.ALT[0])
            variant = (f'{chrom}_{pos}_{ref}_{alt}')
            vcf_info = record.INFO
            vcf_format = record.FORMAT.split(':')
            # assume only one sample per vcf
            vcf_sample = record.samples[0]
            metric_dict = {}
            if not happy:
                # get samplename
                metric_dict['TPFP_or_samplename'] = (
                                query.split('.')[0].split('-')[0]
                                )
                # infer SNP/INDEL status based on ref/alt fields
                metric_dict['snp_indel'] = infer_snp_indel(ref, alt)
                # infer het/hom status based on genotype field
                metric_dict['HETHOM'] = infer_het_hom(vcf_sample['GT'])
            # add info metrics to dictionary
            for key, val in vcf_info.items():
                name = f'info_{key}'
                # catch list values - take only alt #1
                if isinstance(val, list):
                    value = val[0]
                else:
                    value = val
                metric_dict[name] = value
            # add format/genotype metrics to dictionary
            metric_dict.update(
                {f'format_{i}': vcf_sample[i] for i in vcf_format}
            )
            variant_dict[variant] = metric_dict
    except Exception as error:
        print(
            '\nError parsing query VCF. Please check format.\n'
            f'Error: {error}'
            )
        sys.exit(1)
    return variant_dict


def infer_het_hom(genotype):
    '''
    Take genotype field, return het or homalt label

    INPUT
    1 string
    RETURN
    1 string

    TODO - this doesn't cover multiallelics e.g. 2/2 (next version as function
    not used yet)
    '''
    if genotype == '0/0':
        hethom = 'homref'
    elif genotype == '0/1' or genotype == '1/0':
        hethom = 'het'
    elif genotype == '1/1':
        hethom = 'homalt'
    else:
        # not sure whether exiting at this point is best given could be one of
        # thousands - maybe save as N/A and deal with it elsewhere?
        print(
            f'Genotype {genotype} not recognised. Het/hom cannot be inferred.'
            )
        sys.exit(1)
    return hethom


def infer_snp_indel(ref, alt):
    '''
    Take ref & alt fields, return SNP or INDEL label. Input VCF must be
    normalised for this method to work (i.e. one variant per position).
    Possibly redundant as pyvcf has is_SNP or is_Indel methods?

    INPUT
    2 strings
    RETURN
    1 string

    TODO: probably remove func and use pyvcf in parse_query for next version
    '''
    if ',' in alt:
        print(
            f'Comma present in alt field ({alt}), suggesting non-normalised '
            'VCF. Please provide normalised VCF data.'
            )
        sys.exit(1)
    elif len(ref) == 1 and len(alt) == 1:
        snp_indel = 'SNP'
    else:
        snp_indel = 'INDEL'
    return snp_indel


def parse_happy(happy):
    '''
    Takes a Hap.py output vcf containing TP & FP calls. Returns a dictionary
    of variants paired with TP/FP, SNP/INDEL, & het/hom status.

    INPUT
    1 string (happy filename)
    RETURN
    1 dictionary of dictionaries
    '''
    try:
        vcf_reader = vcf.Reader(filename=happy)
        variant_dict = {}
        for record in vcf_reader:
            chrom = record.CHROM
            pos = record.POS
            ref = record.REF
            # take only alt #1 (should only be one anyway)
            alt = record.ALT[0]
            variant = (f'{chrom}_{pos}_{ref}_{alt}')
            # assume query is second sample (should be)
            vcf_sample = record.samples[1]
            cat_dict = {}
            cat_dict['TPFP_or_samplename'] = vcf_sample['BD']
            cat_dict['snp_indel'] = vcf_sample['BVT']
            cat_dict['HETHOM'] = vcf_sample['BLT']
            variant_dict[variant] = cat_dict
    except Exception as error:
        print(
            '\nError parsing happy VCF. Please check format.'
            f'Error: {error}'
            )
        sys.exit(1)
    return variant_dict


def decide_bins(array):
    '''
    Take numpy array & use number and range of values to determine
    appropriate bin number for histopgram. Returns recommended bin size.
    Not in use but may be resurrected if I decide to change histogram defaults.

    INPUT
    1 numpy array
    RETURN
    1 float
    '''
    array_length = len(array)
    array_range = max(array) - min(array)
    # Use modified Sturge's rule to decide number of bins
    num_bins = (1 + 3.322 * math.log10(array_length)) * 3
    # Divide the range of values by the number of bins to get bin size
    bin_size = array_range / num_bins
    return bin_size


def calculate_centiles(vals):
    '''
    Take list of numbers & return a list of equal length representing
    centiles for each value in the input list.

    INPUT
    1 list
    RETURN
    1 numpy array

    TODO - return list instead as I'm just converting it in create_plot()
    anyway
    '''
    centiles = [round(st.percentileofscore(vals, i), 2) for i in vals]
    return np.array(centiles)


def create_plot(plot_list, metric):
    '''
    Given a list of plot datasets, make a tiled image of all the datasets
    as histograms.

    INPUT
    1 list of lists (each with 2 data lists and a filter label), one string
    RETURN
    1 plotly figure object
    '''
    # initialise concat lists
    values = []
    centiles = []
    tpfp = []
    subset = []
    # for each dataset, grab the labels (TP/FP - need to be separated from the
    # main data) and filter (e.g. snp_het), then append to the relevant
    # concatenated lists initialised above
    for plot in plot_list:
        plot_name = plot[-1]
        list1 = plot[0]
        list2 = plot[1]
        label1 = list1.pop(0)
        label2 = list2.pop(0)
        values = values + (list1 + list2)
        centiles = centiles + (
            list(calculate_centiles(list1)) + list(calculate_centiles(list2))
            )
        tpfp = tpfp + (([label1] * len(list1)) + ([label2] * len(list2)))
        subset = subset + ([plot_name] * len(list1 + list2))
    # make dataframe using lists above for columns
    df = pd.DataFrame(
        {'Metric Value': values, 'TPFP': tpfp, 'Centile': centiles,
         'Variant Type': subset}
        )
    # check whether dataframe actually contains data (otherwise will break fig)
    if df.empty:
        if VERBOSE:
            print(f'\nThe metric labelled "{metric}" was requested and listed in '
            'the VCF header, but could not be found in any records. Therefore no '
            'plots can be generated for this metric.\n')
        return None
    # make figure (facet_col tiles the datasets based on filter subset)
    fig = px.histogram(
        df, x='Metric Value', color='TPFP', facet_col='Variant Type',
        hover_data=[df.columns[2]], marginal='rug', barmode='overlay'
        )
    # format the hovertext to display centiles only on the rug plot and counts
    # only on the histogram (rug plots have odd index in histogram)
    for i, trace in enumerate(fig['data']):
        group = trace['legendgroup']
        if i % 2 == 0:
            trace['hovertemplate'] = (
                f'True/False Positive={group}<br>'
                'Bin=%{x}<br>Count=%{y}<extra></extra>'
                )
        else:
            trace['hovertemplate'] = (
                '<br>Metric value=%{x}<br>'
                'Centile=%{customdata[0]}<br><extra></extra>'
                )
    # add vertical line to hover action
    fig.update_layout(hovermode='x unified')
    # specify figure dimensions and titles
    fig.update_layout(
        height=700, width=2000, title_text=metric, showlegend=False
        )
    return fig


def get_output_name(files, happy=True):
    '''
    Parse input filenames and make output filename. Takes list of query files
    (1 or more) and boolean to toggle whether matching happy files are inputs.
    Returns sample1_sample2_QCdist.html if two sample inputs, otherwise
    TPvsFP_samplename_QCdist.html for happy inputs.

    INPUT
    1 list, 1 optional boolean
    RETURN
    1 string
    '''
    if happy:
        sample1 = 'TPvsFP'
    else:
        sample1 = files[0].split('-')[0]
    sample2 = files[1].split('-')[0]
    output = f'{sample1}_{sample2}_QCdist.html'
    return output


def make_html(plots):
    '''
    Given a list of plot objects, construct an html report as a string.
    Output name constructed from input filenames.

    INPUT
    1 list of plotly figure objects
    RETURN
    1 string
    '''
    css = (
        'https://maxcdn.bootstrapcdn.com/bootstrap/3.3.1/css/bootstrap.min.css'
        )
    html_string = (
        f'<html><head><link rel="stylesheet" href="{css}">'
        '<style>body{{ margin:0 100; background:whitesmoke; }}'
        '</style><script src="https://cdn.plot.ly/plotly-2.12.1'
        '.min.js"></script></head><body>'
        '<h1>QC True/False Positive Distributions</h1>'
        '<h4>Each metric requested is plotted below, with separate'
        ' plots for SNP_HET, SNP_HOM, INDEL_HET, & INDEL_HOM variants. Each '
        'axis contains a histogram distribution of the metric values for'
        ' that group, plus a rug plot along the top showing all '
        'datapoints. Hover over the rug plot to get information'
        ' about the metric value at that point and the centile that'
        ' value represents within the data used to generate this '
        'report.</h4>'
        )
    for i in plots:
        metric = i['layout']['title']['text']
        plot_div = pio.to_html(i, full_html=False, include_plotlyjs='cdn')
        html_string = html_string + (
            f'<h2>True & False Positive - {metric}.</h2>'
        )
        html_string = html_string + plot_div

    html_string = html_string + '</body></html>'
    return html_string


def make_report(html_string, outfile):
    '''
    Take html string (output of make_html) and save to output file

    INPUT
    2 strings (one for html, one for output filename)
    RETURN
    nothing if successful, otherwise exception
    '''
    try:
        with open(outfile, 'w') as out:
            out.write(html_string)
    except Exception as error:
        print(
            '\nError saving output to html file.'
            f'Error: {error}'
            )
        sys.exit(1)


def merge_happy_query(happy, query):
    '''
    Take happy dict (output of parse_happy) and query dict (output of
    parse_query) & return new dictionary with matched variants and merged
    values

    INPUT
    2 dictionaries (of dictionaries)
    RETURN
    1 dictionary of dictionaries
    '''
    merged_dict = {}
    missing_variants = []
    for variant in happy:
        try:
            merged_dict[variant] = {**happy[variant], **query[variant]}
        except KeyError:
            missing_variants.append(variant)
    if VERBOSE:
        print(
              '\nThe variants below were present in the hap.py VCF but not '
              f'the query VCF:\n {str(missing_variants)}'
            )
    return merged_dict


def merge_samples(sample1, sample2):
    '''
    Take two dictionaries, merge them, return merged dictionary. Keys now
    contain samplename in case samples share variants.

    INPUT
    2 dictionaries (of dictionaries)
    RETURN
    1 dictionary of dictionaries
    '''
    merged_dict = (
        {f'{SAMPLE1_NAME}-{variant}': sample1[variant] for variant in sample1}
        )
    merged_dict.update(
        {f'{SAMPLE2_NAME}-{variant}': sample2[variant] for variant in sample2}
        )
    return merged_dict


def make_lists(data, metric, fptp, snp_indel, hethom):
    '''
    Take merged dictionary, return two lists (happy vs query, or sample1 vs
    sample2) of relevant metric values for plotting, split according to
    category (SNP/INDEL, het/hom).

    INPUT
    1 dictionary (of dictionaries), 1 string, 1 list, 2 strings
    RETURN
    1 list of lists
    '''
    list1 = [fptp[0]]
    list2 = [fptp[1]]
    # multiallelic variants are labelled 'hetalt' in the happy vcf but they're
    # still hets so capture that possibility
    if hethom == 'het':
        hethom = ['het', 'hetalt']
    # do filtering
    filtered_keys_1 = (
        [k for k, v in data.items() if v['TPFP_or_samplename'] == fptp[0]
         and v['snp_indel'] == snp_indel and v['HETHOM'] in hethom]
        )
    filtered_keys_2 = (
        [k for k, v in data.items() if v['TPFP_or_samplename'] == fptp[1]
         and v['snp_indel'] == snp_indel and v['HETHOM'] in hethom]
        )
    for item in filtered_keys_1:
        # try to append metric value to list but catch occurrences where
        # metric is not present for that variant (usually metrics like
        # BaseQRankSum, ClippingRankSum, ExcessHet, etc.)
        try:
            list1.append(float(data[item][metric]))
        except KeyError:
            pass
    for item in filtered_keys_2:
        try:
            list2.append(float(data[item][metric]))
        except KeyError:
            pass
    return [list1, list2]


def make_plots(data, metrics, happy=True):
    '''
    Take merged data and list of metrics. Return list of plot objects.

    INPUT
    1 dictionary, 1 list, 1 optional boolean
    RETURN
    1 list of plotly figure objects
    '''
    plot_list = []
    if happy:
        fptp = ['TP', 'FP']
    else:
        fptp = [SAMPLE1_NAME, SAMPLE2_NAME]
    for metric in metrics:
        # make filtered lists for each variant category
        snp_het = make_lists(
            data, metric, fptp, snp_indel='SNP', hethom='het'
            )
        snp_hom = make_lists(
            data, metric, fptp, snp_indel='SNP', hethom='homalt'
            )
        indel_het = make_lists(
            data, metric, fptp, snp_indel='INDEL', hethom='het'
            )
        indel_hom = make_lists(
            data, metric, fptp, snp_indel='INDEL', hethom='homalt'
            )
        # add label as another list item
        snp_het.append('snp_het')
        snp_hom.append('snp_hom')
        indel_het.append('indel_het')
        indel_hom.append('indel_hom')
        # make tiled figure
        fig = create_plot([snp_het, snp_hom, indel_het, indel_hom], metric)
        # only append if fig was actually created
        if fig:
            plot_list.append(fig)
    return plot_list


def main():
    '''
    Main app code calling other functions.
    '''
    # get command line arguments
    args = get_args()
    if args.happy:
        get_sample_names(args.happy, args.query[0])
        # check that sample names match between happy and query files
        check_happy_query_match(SAMPLE1_NAME, SAMPLE2_NAME)
        # check metrics are available
        metrics = check_metrics(args.query[0], args.metrics)
        # parse inputs
        sample1 = parse_happy(args.happy)
        sample2 = parse_query(args.query[0])
        # merge input dicts
        merged_data = merge_happy_query(sample1, sample2)
        # make 4 lists for snp, indel, het, hom plots, for each metric
        # & make plot objects
        plots = make_plots(merged_data, metrics)
    else:
        get_sample_names(args.query[0], args.query[1])
        # check metrics are available
        print("Dual sample inputs not yet implemented\n")
        sys.exit(1)
        metrics = check_multiple_query_metrics(args.query, args.metrics)
        # parse inputs
        sample1 = parse_query(args.query[0], False)
        sample2 = parse_query(args.query[1], False)
        # merge input dicts
        merged_data = merge_samples(sample1, sample2, False)
        # make 4 arrays for snp, indel, het, hom plots
        plots = make_plots(merged_data, metrics, happy=False)

    # generate output filename
    if args.happy:
        output = get_output_name([args.happy, args.query[0]])
    else:
        output = get_output_name(args.query, False)

    # for each metric in plots list, add to report
    html_output = make_html(plots)
    make_report(html_output, output)


if __name__ == "__main__":
    main()