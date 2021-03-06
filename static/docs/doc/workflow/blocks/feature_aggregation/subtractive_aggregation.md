
[Home](../../../index.html) > [Categories](../../index.html) > [Feature Aggregation](index.html)

# Subtractive aggregation

* Category: Feature Aggregation

## Inputs

* *mRNA_es [[ExpressionSet](../../../data_types.html#expressionset)]*
* *miRNA_es [[ExpressionSet](../../../data_types.html#expressionset)]*
* *interaction [[BinaryInteraction](../../../data_types.html#binaryinteraction)]*

## Parameters

* *Constant c* - the real valued general strength of miRNA-mRNA interactions
* *a bigger value puts more emphasis on the prior knowledge. The zero value means no influence of miRNAs. If the data are normalized
* *the upper bound-value is possible to estimate as the mean cardinality of mRNA-miRNA interactions.

## Outputs

* *agg_es[[ExpressionSet](../../../data_types.html#expressionset)]*

## Description

  the method for mRNA and miRNA data aggregation based on the known miRNA targets, the main idea is to use the knowledge of miRNA targets and better approximate the actual protein amount synthesized in the sample, miRNAs mostly downregulate its targets, for this reason, miRNA activity gets subtracted from mRNA expression of its targets, the strength of subtraction is given by the c constant (the value of 1 is used as default), the outcome is a modified mRNA set

## Examples of Usage
        