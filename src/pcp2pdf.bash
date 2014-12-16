# pcp2pdf completion
# FIXME: implement this
#_pcp2pdf()
#{
#    local cur prev opts
#    COMPREPLY=()
#    cur="${COMP_WORDS[COMP_CWORD]}"
#    prev="${COMP_WORDS[COMP_CWORD-1]}"
#    opts="--help --verbose --version"
#
#    if [[ ${cur} == -* ]] ; then
#        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
#        return 0
#    fi
#} && complete -F _pcp2pdf pcp2pdf

# Local variables:
# mode: shell-script
# sh-basic-offset: 4
# sh-indent-comment: t
# indent-tabs-mode: nil
# End:
# ex: ts=4 sw=4 et filetype=sh
