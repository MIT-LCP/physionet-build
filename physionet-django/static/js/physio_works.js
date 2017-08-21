function change(item){ 
    glyphicon = document.getElementById(item);
    if (glyphicon.className == "glyphicon glyphicon-chevron-down pull-right"){
        glyphicon.className = "glyphicon glyphicon-chevron-right pull-right";
    }
    else{
        glyphicon.className = "glyphicon glyphicon-chevron-down pull-right";
    }
}

$( "#id_Type-projecttype_0" ).change(function() {
    document.getElementById('Toolkit-Panel').style.display  = 'none'; 
    // document.getElementById('Turorial-Panel').style.display = 'none'; 
    document.getElementById('Database-Panel').style.display = 'block'; 
});
$( "#id_Type-projecttype_1" ).change(function() {
    document.getElementById('Database-Panel').style.display = 'none'; 
    // document.getElementById('Turorial-Panel').style.display = 'none'; 
    document.getElementById('Toolkit-Panel').style.display = 'block'; 
});
$( "#id_Type-projecttype_2" ).change(function() {
    document.getElementById('Toolkit-Panel').style.display = 'none'; 
    document.getElementById('Database-Panel').style.display = 'none'; 
    // document.getElementById('Turorial-Panel').style.display = 'block'; 
});
$('.link-formset').formset({
    addText: 'Add link',
    deleteText: 'Remove',
    prefix: 'link_page'
});

$('.collaborators-formset').formset({
    addText: 'Add Colaborator',
    deleteText: 'Remove',
    prefix: 'colab'
});