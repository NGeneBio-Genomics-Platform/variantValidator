"""
Exon_numbering

Authors: Katie Williams (@kwi11iams) and Katherine Winfield (@kjwinfield)

This code will ultimately aim to provide exon numbering information for VariantValidator

"""

# Import the relevant packages/functions
import requests #this is needed to talk to the API
import json #this is needed to format the output data
import re

# Define all the URL information as strings
base_url_VV = "https://rest.variantvalidator.org/"
server_G2T = "VariantValidator/tools/gene2transcripts/"
gene_query = "BRCA1"
server_variant = 'VariantValidator/variantvalidator/'
genome_build = "GRCh38"

# Define the parameter for retrieving in a JSON format
parameters = '?content-type=application/json'

# Create a function that will call an API and retrieve the information
def request_sequence(base_url, server, gene_name, parameters):
    url = base_url + server + gene_name + parameters

    # make the request and pass the object to the function
    response = requests.get(url) #this is the code that actually queries the API
    print("Querying " + url)
    return response


############ FUNCTION 1 ######################################################
# Use a variant ID, and call VV API
# This is a check

# Pre-determine the variant
variant_id = "NM_007294.3:c.1067A>G"

# Query the VV API with the variant
variant_response = request_sequence(base_url_VV, server_variant, genome_build + '/' + variant_id + '/all', parameters)

# Convert the response (JSON) to a python dictionary
variant_response_dictionary = variant_response.json()

# Print response
#print(json.dumps(variant_response_dictionary, sort_keys=True, indent=4, separators=(',', ': ')))


####### FUNCTION 2 #########################################################
# Code to request BRCA1 data from the gene2transcripts VariantValidator API 

# First, do using gene_query as "BRCA1"
# response = request_sequence(base_url_VV, server_G2T, gene_query, parameters)
# response_dictionary = response.json()

# Print the response
# print(json.dumps(response_dictionary, sort_keys=True, indent=4, separators=(',', ': ')))

# Now, rather than the gene symbol BRCA1, it pass a transcript ID
transcript_id = variant_id.split(":")[0]
response = request_sequence(base_url_VV, server_G2T, transcript_id, parameters)
response_dictionary = response.json()
# Print the response
#print(json.dumps(response_dictionary, sort_keys=True, indent=4, separators=(',', ': ')))

# Note, function 2 will pull back the exon structures for all the transcripts
# so will need to filter out the transcript you are interested in based on the transcript ID.

#this for loop finds the exon structure for the given transcript
num_transcripts = len(response_dictionary["transcripts"])
for i in range(num_transcripts):
    if response_dictionary["transcripts"][i]["reference"] == transcript_id:
        transcipt_accession = i
        #returns an exon structure dictionary
        brca_exon_structure = response_dictionary["transcripts"][i]["genomic_spans"]
        break

#print(brca_exon_structure.keys())
#print(brca_exon_structure)

####### FUNCTION 3 #########################################################
# Works out the exon/intron for the transcript variant for each aligned chromosomal or gene reference sequence
# Set up output dictionary  
#exon_start_end_positions = {}
# This dictionary will have the keys as the aligned chromosomal and gene reference sequences
# And the values of these keys will be another dictionary
# With keys, start_exon and end_exon
# With respective values relating the the position of variant in the reference seqeuence
# e.g. {NC_000: {"start_exon": "1", "end_exon": "1i"}, NC_0000 .... 

 
# Find transcript coordinates (this only works for a SNP, need to adapt for variants that range over more than one nucleotide)
variant_pos = variant_id.split(":")[1].split(".")[1]
variant_pos = re.sub('[^0-9, +, -, _]','', variant_pos) #removes A,G,C,T from HGVS nomenclature
print(variant_pos)


#function to find exon number for a given variant 
def finds_exon_number(coordinates, exon_structure_dict=brca_exon_structure):

    #identify start and end of variant from input coordinates
    if '_' in coordinates:
        split = coordinates.split('_')
        start_position = split[0]
        end_position = split[1]
    else:
        end_position = coordinates
        start_position = coordinates
    
    exon_start_end_positions = {}
    for transcript in exon_structure_dict.keys():
        for exon in exon_structure_dict[transcript]['exon_structure']:

            #runs to identify which exon the variant is in 
            #start position
            if '+' or '-' not in start_position:
                start_position = int(start_position)
                if start_position >= exon['transcript_start'] and start_position <= exon['transcript_end']:
                    start_exon = str(exon['exon_number'])
            
            elif '+' in start_position:
                exon_end = start_position.split('+')[0]
                exon_end = int(exon_end)
                if exon_end == exon['transcript_end']:
                    start_exon = str(exon['exon_number']) + 'i'
            
            elif '-' in start_position:
                exon_start = start_position.split('-')[0]
                exon_start = int(exon_start)
                if exon_end == exon['transcript_start']:
                    start_exon = str(exon['exon_number'] - 1)+ 'i'
            #end position
            if  '+' or '-' not in end_position:
                end_position = int(end_position)
                if end_position >= exon['transcript_start'] and end_position <= exon['transcript_end']:
                    end_exon = str(exon['exon_number'])
                 
            elif '+' in end_position:
                exon_end = end_position.split('+')[0]
                exon_end = int(exon_end)
                if exon_end == exon['transcript_end']:
                    end_exon =  str(exon['exon_number'])+ 'i'
            
            elif '-' in end_position:
                exon_start = start_position.split('-')[0]
                exon_start = int(exon_start)           
                if end_position >= exon['transcript_start'] and end_position <= exon['transcript_end']:
                    end_exon = str(exon['exon_number'] - 1) + 'i'

        exon_start_end_positions[transcript] = {"start_exon": start_exon, "end_exon": end_exon}
    return exon_start_end_positions

#test for our variant
print(finds_exon_number(variant_pos))


#create dictionary of all intron exon positions for transcripts
# for transcript_id in variant_response_dictionary:
#     exon_start_end_positions[transcript_id] = {"start_exon": start_exon, "end_exon": end_exon}

'''
define function to parse through exon_start_end_positions and return the intron
and exon numbering for the start and end of the query variant
'''
# def finds_variant_in_dict(reference):
#     for transcript_id in exon_start_end_positions:
#         if transcript_id == reference:
#             print("The exon numbering for " + transcript_id + " starts in " + start_exon + " ends in " + end_exon)

#close